"""Local, versioned sessions. Model I/O occurs outside the generation lock."""
import copy
import hashlib
import json
import time
import uuid

from pydantic import ValidationError as SchemaError

from backend.ai_protocol import Interpretation, PROMPT_VERSION, apply_operations, parameter_message
from backend.model_client import ModelClient
from backend.service import ServiceError, write_json
from scripts.generate_equipment import validate_request
from scripts.generate_mod import ValidationError


class AIService:
    def __init__(self, equipment, model=None):
        self.equipment = equipment
        self.model = model or ModelClient()
        self.active = set()

    def path(self, session_id):
        try:
            identifier = str(uuid.UUID(session_id))
        except (ValueError, AttributeError):
            raise ServiceError('unknown_session', '会话不存在。', 404)
        return self.equipment.root / 'ai_sessions' / (identifier + '.json')

    def save(self, state):
        write_json(self.path(state['session_id']), state)

    def read(self, session_id):
        path = self.path(session_id)
        if not path.exists():
            raise ServiceError('unknown_session', '会话不存在。', 404)
        state = json.loads(path.read_text(encoding='utf-8'))
        # A previous process may have stopped during a network request.
        if state['inflight'] and session_id not in self.active:
            state['requests'][state['inflight']]['error'] = {'code': 'request_interrupted', 'message': '请求被中断，请使用新请求编号重试。', 'status': 409}
            state['inflight'] = None
            self.save(state)
        return state

    @staticmethod
    def public(state):
        return {k: copy.deepcopy(v) for k, v in state.items() if k not in ('requests', 'catalog_sha256')}

    def get(self, session_id):
        with self.equipment.lock:
            state = self.read(session_id)
            if state['preview']:
                state['preview'] = self.equipment.read(state['preview']['plan_id'])
                state['preview'].pop('error', None)
            return self.public(state)

    def create(self, object_id):
        with self.equipment.lock:
            detail = self.equipment.detail(object_id)
            state = {'session_id': str(uuid.uuid4()), 'object': object_id, 'version': 0,
                     'catalog_sha256': self.equipment.versions()['catalog_sha256'],
                     'detail': {k: detail[k] for k in ('display_name', 'original', 'field_rules', 'scope', 'capabilities')},
                     'draft': {}, 'questions': [], 'unsupported': [], 'history': [],
                     'status': 'empty', 'explanation': '', 'trace': [], 'preview': None,
                     'requests': {}, 'inflight': None}
            self.save(state)
            return self.public(state)

    def check_version(self, state, version):
        if state['catalog_sha256'] != self.equipment.versions()['catalog_sha256']:
            raise ServiceError('stale_catalog', '目录已变化，请重新选择装备并核对参数。')
        if state['version'] != version:
            raise ServiceError('stale_session', '草稿版本已变化，请重新读取会话。')
        if state['inflight']:
            raise ServiceError('session_busy', '当前会话正在处理请求，请等待。')

    def begin(self, session_id, body, kind):
        state = self.read(session_id)
        fingerprint = hashlib.sha256(json.dumps({'kind': kind, **body}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        previous = state['requests'].get(body['request_id'])
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise ServiceError('request_id_conflict', '同一请求编号不能用于不同内容。')
            if 'error' in previous:
                error = previous['error']
                raise ServiceError(error['code'], error['message'], error['status'])
            if state['inflight'] == body['request_id']:
                raise ServiceError('session_busy', '同一请求仍在处理。')
            return state, True
        self.check_version(state, body['version'])
        state['requests'][body['request_id']] = {'fingerprint': fingerprint}
        return state, False

    def context(self, state, text):
        return {'object': state['detail'], 'draft': state['draft'], 'questions': state['questions'],
                'unsupported': state['unsupported'], 'recent_turns': state['history'][-6:], 'text': text}

    def message(self, session_id, body):
        with self.equipment.lock:
            state, replay = self.begin(session_id, body, 'message')
            if replay:
                return self.public(state)
            state['inflight'] = body['request_id']
            self.active.add(session_id)
            self.save(state)
            context = self.context(state, body['text'])
        started = time.monotonic()
        usage = None
        interpretation = None
        output = None
        error = None
        try:
            output, usage = self.model.parse(context)
            interpretation = Interpretation.model_validate(output)
            draft, trace = apply_operations(state['object'], state['draft'], interpretation, self.equipment.catalog())
        except SchemaError:
            error = ServiceError('model_invalid_output', '模型输出未通过结构校验；草稿未改变，请重试或手动填写。', 502)
        except ValidationError as exc:
            error = ServiceError('invalid_parameters', parameter_message(exc), 422)
        except ServiceError as exc:
            error = exc
        except Exception:
            error = ServiceError('model_internal_error', '解析服务异常；草稿未改变，可以重试。', 500)
        with self.equipment.lock:
            current = self.read(session_id)
            current['inflight'] = None
            self.active.discard(session_id)
            if current['catalog_sha256'] != self.equipment.versions()['catalog_sha256']:
                error = ServiceError('stale_catalog', '目录已变化，请重新选择装备。')
            if current['version'] != body['version']:
                error = ServiceError('stale_session', '响应已过期，未覆盖新草稿。')
            event = {'request_id': body['request_id'], 'text': body['text'], 'prompt_version': PROMPT_VERSION,
                     'model': self.model.model, 'version_before': current['version'],
                     'elapsed_ms': round((time.monotonic() - started) * 1000), 'usage': usage,
                     'interpretation': interpretation.model_dump() if interpretation else None,
                     'invalid_model_output': output if interpretation is None else None}
            if error:
                event['error'] = {'code': error.code, 'message': error.message, 'status': error.status}
                current['requests'][body['request_id']]['error'] = event['error']
            else:
                current.update(draft=draft, trace=trace, questions=interpretation.questions,
                               unsupported=list(dict.fromkeys(current['unsupported'] + interpretation.unsupported)),
                               explanation=interpretation.explanation, status=interpretation.result,
                               version=current['version'] + 1, preview=None)
            event['version_after'] = current['version']
            current['history'].append(event)
            self.save(current)
            if error:
                raise error
            return self.public(current)

    def manual(self, session_id, body):
        with self.equipment.lock:
            state, replay = self.begin(session_id, body, 'draft')
            if replay:
                return self.public(state)
            changes = body['changes']
            if changes:
                clean, _ = validate_request({'object': state['object'], 'changes': changes},
                                           catalog=self.equipment.catalog(), allow_unverified=True)
                changes = clean['changes']
            if state['unsupported'] and not body['accept_supported_only']:
                raise ServiceError('unsupported_ack_required', '请明确选择仅继续支持部分，或重新选择装备开始。')
            state.update(draft=changes, questions=[], unsupported=[], trace=[], preview=None,
                         version=state['version'] + 1, status='suggestion' if changes else 'empty',
                         explanation='已保存手动参数；此前未解决要求以本次完整参数为准。')
            state['history'].append({'request_id': body['request_id'], 'kind': 'manual', 'changes': changes,
                                     'accepted_supported_only': body['accept_supported_only'], 'version_after': state['version']})
            self.save(state)
            return self.public(state)

    def preview(self, session_id, body):
        with self.equipment.lock:
            state, replay = self.begin(session_id, body, 'preview')
            if replay:
                return self.public(state)
            if state['questions'] or state['unsupported'] or not state['draft']:
                raise ServiceError('unresolved_draft', '请先解决澄清或不支持要求，并填写至少一项修改。')
            plan = self.equipment.preview({'object': state['object'], 'changes': state['draft']})
            plan.update(ai_session=session_id, ai_version=state['version'])
            write_json(self.equipment.path(plan['plan_id']), plan)
            state['preview'] = plan
            self.save(state)
            return self.public(state)
