import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.ai_protocol import Interpretation, apply_operations
from backend.ai_service import AIService
from backend.model_client import ModelClient, settings, connection
from backend.service import EquipmentService, ServiceError, write_json
from scripts.generate_equipment import FIRST_BLOOD
from scripts.generate_mod import ValidationError


def op(field='weight_kg', operation='multiply', value=.5, basis='current', unit=None):
    return dict(field=field, operation=operation, value=value, basis=basis, unit=unit)


def result(*operations, questions=None, unsupported=None):
    return dict(result='clarify' if questions else ('unsupported' if unsupported and not operations else 'suggestion'),
                operations=list(operations), questions=questions or [], unsupported=unsupported or [], explanation='测试解释')


class FakeModel:
    model = 'mock-only'

    def __init__(self):
        self.output = result(op())
        self.calls = 0
        self.context = None

    def parse(self, context):
        self.calls += 1
        self.context = context
        if isinstance(self.output, Exception):
            raise self.output
        return copy.deepcopy(self.output), None


class AITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = EquipmentService(root=Path(self.temp.name))
        self.model = FakeModel()
        self.ai = AIService(self.service, self.model)
        self.state = self.ai.create(FIRST_BLOOD)
        self.counter = 0

    def body(self, **extra):
        self.counter += 1
        return dict(version=self.state['version'], request_id=str(self.counter), **extra)

    def send(self, output=None, text='重量减半'):
        if output is not None:
            self.model.output = output
        self.state = self.ai.message(self.state['session_id'], self.body(text=text))
        return self.state

    def manual(self, changes, accept=False):
        self.state = self.ai.manual(self.state['session_id'], self.body(changes=changes, accept_supported_only=accept))
        return self.state

    def preview(self):
        self.state = self.ai.preview(self.state['session_id'], self.body())
        return self.state['preview']

    def test_relative_original_and_revoke(self):
        original = float(self.state['detail']['original']['Weight'])
        self.send(result(op(), op('name', 'set', '月影')))
        self.assertEqual(self.state['draft']['weight_kg'], original / 2)
        self.send(result(op()))
        self.assertEqual(self.state['draft']['weight_kg'], original / 4)
        self.send(result(op(basis='original'), op('name', 'remove', None)))
        self.assertEqual(self.state['draft'], {'weight_kg': original / 2})

    def test_grams_add_subtract(self):
        self.send(result(op(operation='set', value=1250, unit='g')))
        self.send(result(op(operation='add', value=250, unit='g')))
        self.assertEqual(self.state['draft']['weight_kg'], 1.5)
        self.send(result(op(operation='subtract', value=.5, unit='kg')))
        self.assertEqual(self.state['draft']['weight_kg'], 1)

    def test_bad_values_atomic(self):
        for value in [-1, 101, .0001]:
            with self.subTest(value=value):
                with self.assertRaises(ServiceError) as caught:
                    self.send(result(op('name', 'set', '不能残留'), op(operation='set', value=value, unit='kg')))
                self.assertEqual(caught.exception.code, 'invalid_parameters')
                self.assertEqual(self.ai.get(self.state['session_id'])['draft'], {})

    def test_schema_and_unsupported_field(self):
        bad = [result(op('unknown', 'set', 'x')), result(op(value=True)), result(op(), op()),
               {**result(), 'generate': True}, result(op('name', 'multiply', 2)), result(op(value='0.5'))]
        for output in bad:
            with self.subTest(output=output), self.assertRaises(ServiceError) as caught:
                self.send(output)
            self.assertEqual(caught.exception.code, 'model_invalid_output')
        self.assertEqual(self.ai.get(self.state['session_id'])['version'], 0)

    def test_capability_and_missing_original(self):
        catalog = self.service.catalog()
        catalog['items'][FIRST_BLOOD]['capabilities'] = []
        with self.assertRaises(ValidationError):
            apply_operations(FIRST_BLOOD, {}, Interpretation.model_validate(result(op())), catalog)
        catalog = self.service.catalog()
        catalog['items'][FIRST_BLOOD]['original']['Weight'] = None
        with self.assertRaises(ValidationError):
            apply_operations(FIRST_BLOOD, {}, Interpretation.model_validate(result(op())), catalog)

    def test_five_fields_on_capable_object(self):
        catalog = self.service.catalog()
        item = next(i for i in catalog['items'].values() if set(['damage','versatile_damage','weight_kg','name','rarity']) <= set(i['capabilities']))
        values = {'damage':'2d6','versatile_damage':'2d8','weight_kg':1.125,'name':'月影','rarity':'Rare'}
        parsed = Interpretation.model_validate(result(*(op(k,'set',v,unit='kg' if k=='weight_kg' else None) for k,v in values.items())))
        draft, _ = apply_operations(item['object_id'], {}, parsed, catalog)
        self.assertEqual(draft, values)

    def test_mixed_and_manual_ack(self):
        self.send(result(op(), unsupported=['召唤技能']))
        with self.assertRaises(ServiceError):
            self.preview()
        self.send(result())  # Saying OK cannot silently clear unsupported intent.
        with self.assertRaises(ServiceError):
            self.preview()
        with self.assertRaises(ServiceError):
            self.manual(self.state['draft'])
        self.manual(self.state['draft'], True)
        self.assertTrue(self.preview()['plan_id'])

    def test_clarification_and_empty_draft(self):
        self.send(result(questions=['哪一项增强？']))
        with self.assertRaises(ServiceError):
            self.preview()
        self.send(result(op('damage','set','2d6')))
        self.assertTrue(self.preview())
        self.manual({})
        with self.assertRaises(ServiceError):
            self.preview()

    def test_duplicate_stale_and_conflict(self):
        body = self.body(text='重量减半')
        self.state = self.ai.message(self.state['session_id'], body)
        draft = self.state['draft']
        self.assertEqual(self.ai.message(self.state['session_id'], body)['draft'], draft)
        self.assertEqual(self.model.calls, 1)
        with self.assertRaises(ServiceError):
            self.ai.message(self.state['session_id'], {**body, 'text':'再减半'})
        with self.assertRaises(ServiceError):
            self.ai.message(self.state['session_id'], {**body, 'request_id':'new'})

    def test_failure_retry_and_history(self):
        self.send()
        before = copy.deepcopy(self.state)
        self.model.output = ServiceError('model_timeout', '超时', 504)
        body = self.body(text='再次减半')
        for _ in range(2):
            with self.assertRaises(ServiceError):
                self.ai.message(self.state['session_id'], body)
        after = self.ai.get(self.state['session_id'])
        self.assertEqual(after['draft'], before['draft'])
        self.assertEqual(after['version'], before['version'])
        self.assertEqual(after['history'][-1]['text'], '再次减半')
        self.assertEqual(self.model.calls, 2)
        self.manual({'weight_kg':1})

    def test_old_preview_and_confirmation(self):
        self.send(result(op('damage','set','2d6')))
        plan = self.preview()
        with self.assertRaises(ServiceError) as caught:
            self.service.confirm_generate(plan['plan_id'], False, False)
        self.assertEqual(caught.exception.code, 'confirmation_required')
        self.manual({'damage':'3d6'})
        with self.assertRaises(ServiceError) as caught:
            self.service.confirm_generate(plan['plan_id'], True, True)
        self.assertEqual(caught.exception.code, 'stale_ai_preview')

    def test_catalog_change_and_restart(self):
        self.send()
        restored = AIService(self.service, self.model).get(self.state['session_id'])
        self.assertEqual(restored['draft'], self.state['draft'])
        with patch.object(self.service, 'versions', return_value={'catalog_sha256':'changed'}):
            with self.assertRaises(ServiceError) as caught:
                self.preview()
            self.assertEqual(caught.exception.code, 'stale_catalog')

    def test_context_last_six_and_no_cross_object(self):
        for _ in range(8):
            self.send(result(op('name','set','月影')))
        self.assertEqual(len(self.model.context['recent_turns']), 6)
        self.assertNotIn('object_id', self.model.context['object'])
        self.assertEqual(self.ai.create(FIRST_BLOOD)['draft'], {})

    def test_busy_blocks_generation_and_draft(self):
        self.send(result(op('damage','set','2d6')))
        plan = self.preview()
        entered, release = threading.Event(), threading.Event()
        def blocking(context):
            entered.set()
            release.wait(5)
            return result(op()), None
        self.model.parse = blocking
        outcomes = []
        thread = threading.Thread(target=lambda: outcomes.append(self.ai.message(self.state['session_id'], self.body(text='减半'))))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(ServiceError):
                self.manual({'damage':'3d6'})
            with self.assertRaises(ServiceError):
                self.service.confirm_generate(plan['plan_id'], True, True)
        finally:
            release.set()
            thread.join(5)
        self.assertEqual(len(outcomes), 1)

    def test_http_contract_and_demo(self):
        with TestClient(create_app(self.service, self.model)) as client:
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.get('/demo-assets/app.js').status_code, 200)
            response = client.post('/api/ai/sessions', json={'object':FIRST_BLOOD})
            self.assertEqual(response.status_code, 201)
            session = response.json()
            path = '/api/ai/sessions/'+session['session_id']
            for bad in [{'version':True,'request_id':'a','text':'x'}, {'version':0,'request_id':'a','text':'   '},
                        {'version':0,'request_id':'a','text':'x','confirmed':True}]:
                self.assertEqual(client.post(path+'/messages', json=bad).status_code, 422)
            self.assertEqual(client.post(path+'/messages',json={'version':0,'request_id':'a','text':'减半'}).status_code,200)
            self.assertEqual(client.get(path).json()['version'],1)
            self.assertEqual(client.post(path+'/preview',json={'version':1,'request_id':'b'}).status_code,200)
            invalid = client.post(path+'/draft',json={'version':1,'request_id':'c','changes':{'weight_kg':101}})
            self.assertEqual(invalid.status_code,422)
            self.assertIn('重量',invalid.json()['detail']['message'])

    def test_interrupted_request_recovery(self):
        state = self.ai.read(self.state['session_id'])
        state['inflight'] = 'interrupted'
        state['requests']['interrupted'] = {'fingerprint':'unused'}
        self.ai.save(state)
        recovered = AIService(self.service, self.model).get(state['session_id'])
        self.assertIsNone(recovered['inflight'])
        self.manual({'damage':'2d6'})
        self.assertTrue(self.preview())

    def test_stale_model_response_never_overwrites(self):
        def change_during_call(context):
            state = self.ai.read(self.state['session_id'])
            state.update(version=state['version']+1, draft={'name':'保留新草稿'})
            self.ai.save(state)
            return result(op()), None
        self.model.parse = change_during_call
        with self.assertRaises(ServiceError) as caught:
            self.send()
        self.assertEqual(caught.exception.code, 'stale_session')
        self.assertEqual(self.ai.get(self.state['session_id'])['draft'], {'name':'保留新草稿'})

    def test_chat_confirmation_never_generates_and_failure_keeps_preview(self):
        self.send(result(op('damage','set','2d6')))
        plan = self.preview()
        self.model.output = ServiceError('model_timeout','timeout',504)
        with self.assertRaises(ServiceError):
            self.send(text='确认并生成')
        self.assertEqual(self.ai.get(self.state['session_id'])['preview']['plan_id'],plan['plan_id'])
        self.assertEqual(self.service.read(plan['plan_id'])['status'],'preview')
        self.send(result(),text='确认并生成')
        self.assertEqual(self.service.read(plan['plan_id'])['status'],'preview')

    def test_completed_artifact_survives_draft_change(self):
        self.send(result(op('damage','set','2d6')))
        plan = self.preview()
        plan['status'] = 'succeeded'
        write_json(self.service.path(plan['plan_id']),plan)
        self.manual({'damage':'3d6'})
        self.assertEqual(self.service.confirm_generate(plan['plan_id'], True, False)['status'],'succeeded')


class ModelClientTests(unittest.TestCase):
    def test_environment_precedence(self):
        with patch.dict('os.environ', {'DEEPSEEK_API_KEY':'environment-test', 'DEEPSEEK_MODEL':'test-model'}):
            config=settings()
        self.assertEqual(config['DEEPSEEK_API_KEY'],'environment-test')
        self.assertEqual(config['DEEPSEEK_MODEL'],'test-model')

    def client(self, handler):
        client = ModelClient(httpx.MockTransport(handler))
        client.config.update(MODEL_PROVIDER='deepseek',MODEL_NAME='',MODEL_BASE_URL='',MODEL_USE_SYSTEM_PROXY='')
        client.config['DEEPSEEK_API_KEY'] = 'test-only'
        return client

    def test_json_payload_and_usage(self):
        def handler(request):
            payload=json.loads(request.content)
            self.assertEqual(payload['response_format'],{'type':'json_object'})
            self.assertFalse(payload['stream'])
            self.assertEqual(payload['thinking'], {'type':'disabled'})
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result(op()))}}], 'usage':{'total_tokens':10}})
        parsed, usage = self.client(handler).parse({'text':'减半'})
        self.assertEqual(parsed['operations'][0]['value'],.5)
        self.assertEqual(usage['total_tokens'],10)

    def test_diagnostics_record_stages_without_payload_or_credentials(self):
        client = self.client(lambda request: httpx.Response(200, json={
            'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result(op()))}}]}))
        client.parse({'text':'private-user-text'})
        diagnostic = client.diagnostics
        stages = [row['stage'] for row in diagnostic['stages']]
        self.assertEqual(stages, ['request_started','provider_configured','network_route','response_headers','first_body_chunk','body_complete','completed'])
        serialized=json.dumps(diagnostic)
        for secret in ['private-user-text','test-only','Authorization','reasoning_content']:
            self.assertNotIn(secret,serialized)

    def test_stream_read_error_preserves_response_stage(self):
        class BrokenBody(httpx.SyncByteStream):
            def __iter__(self):
                yield b' '
                raise httpx.ReadTimeout('private-error-detail')
        client=self.client(lambda request:httpx.Response(200,stream=BrokenBody()))
        with self.assertRaises(ServiceError) as caught:
            client.parse({})
        self.assertEqual(caught.exception.code,'model_timeout')
        stages=[row['stage'] for row in client.diagnostics['stages']]
        self.assertIn('response_headers',stages)
        self.assertIn('first_body_chunk',stages)
        self.assertNotIn('body_complete',stages)
        self.assertNotIn('private-error-detail',json.dumps(client.diagnostics))

    def test_proxy_is_explicit_and_overload_is_not_output_error(self):
        client=self.client(lambda request:httpx.Response(503,json={'error':{'message':'busy'}}))
        client.config['DEEPSEEK_USE_SYSTEM_PROXY']='1'
        with self.assertRaises(ServiceError) as caught:
            client.parse({})
        self.assertEqual(caught.exception.code,'model_overloaded')
        self.assertEqual(caught.exception.status,503)
        route=next(row for row in client.diagnostics['stages'] if row['stage']=='network_route')
        self.assertTrue(route['system_proxy'])
        self.assertNotIn('first_body_chunk',[row['stage'] for row in client.diagnostics['stages']])

    def test_errors(self):
        cases=[(401,{},'model_auth_failed'),(429,{},'model_rate_limited'),
               (402,{},'model_insufficient_balance'),(503,{},'model_overloaded'),
               (200,{'error':{'type':'service_unavailable_error'}},'model_overloaded'),
               (200,{},'model_invalid_output'),
               (200,{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},'model_incomplete'),
               (200,{'choices':[{'finish_reason':'stop','message':{'content':''}}]},'model_empty'),
               (200,{'choices':[{'finish_reason':'stop','message':{'content':'{"a":1,"a":2}'}}]},'model_invalid_output')]
        for status, data, code in cases:
            with self.subTest(code=code), self.assertRaises(ServiceError) as caught:
                self.client(lambda req:httpx.Response(status,json=data)).parse({})
            self.assertEqual(caught.exception.code, code)
        def timeout(req):
            raise httpx.ReadTimeout('test')
        with self.assertRaises(ServiceError) as caught:
            self.client(timeout).parse({})
        self.assertEqual(caught.exception.code,'model_timeout')

    def test_bailian_token_plan_payload_and_separate_credentials(self):
        def handler(request):
            self.assertEqual(str(request.url),'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions')
            self.assertEqual(request.headers['authorization'],'Bearer token-plan-test')
            payload=json.loads(request.content)
            self.assertEqual(payload['model'],'qwen3.7-plus')
            self.assertIs(payload['enable_thinking'],False)
            self.assertNotIn('thinking',payload)
            self.assertEqual(payload['response_format'],{'type':'json_object'})
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result(op()))}}], 'usage':{'total_tokens':23}})
        client=self.client(handler)
        client.config.update(MODEL_PROVIDER='bailian',MODEL_NAME='qwen3.7-plus',
            MODEL_BASE_URL='https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
            BAILIAN_TOKEN_PLAN_API_KEY='token-plan-test',DASHSCOPE_API_KEY='must-not-use')
        output,usage=client.parse({'text':'重量减半'})
        self.assertEqual(usage['total_tokens'],23)
        self.assertEqual(client.model,'qwen3.7-plus')
        self.assertEqual(client.provider,'bailian')

    def test_provider_key_missing_never_falls_back_or_calls_network(self):
        def forbidden(request):raise AssertionError('No request expected')
        client=self.client(forbidden)
        client.config.update(MODEL_PROVIDER='bailian',MODEL_BASE_URL='',DASHSCOPE_API_KEY='')
        with self.assertRaises(ServiceError) as caught:client.parse({})
        self.assertEqual(caught.exception.code,'model_not_configured')

    def test_provider_host_mismatch_rejected_before_credentials_sent(self):
        client=self.client(lambda request:(_ for _ in ()).throw(AssertionError('No request expected')))
        for url in ['https://untrusted.example/compatible-mode/v1',
                    'https://api.deepseek.com/compatible-mode/v1',
                    'http://dashscope.aliyuncs.com/compatible-mode/v1',
                    'https://dashscope.aliyuncs.com/compatible-mode/v1?key=private']:
            client.config.update(MODEL_PROVIDER='bailian',MODEL_BASE_URL=url,DASHSCOPE_API_KEY='private')
            with self.assertRaises(ServiceError) as caught:client.parse({})
            self.assertEqual(caught.exception.code,'model_config_invalid')

    def test_standard_bailian_endpoint_and_provider_error_text(self):
        client=self.client(lambda request:httpx.Response(503,json={}))
        client.config.update(MODEL_PROVIDER='bailian',MODEL_BASE_URL='',MODEL_NAME='',DASHSCOPE_API_KEY='dashscope-test')
        selected=connection(client.config)
        self.assertEqual(selected['model'],'qwen-plus')
        self.assertEqual(selected['key_name'],'DASHSCOPE_API_KEY')
        with self.assertRaises(ServiceError) as caught:client.parse({})
        self.assertIn('阿里云百炼',caught.exception.message)
        self.assertNotIn('DeepSeek',caught.exception.message)


if __name__ == '__main__':
    unittest.main()
