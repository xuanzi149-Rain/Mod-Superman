"""One bounded model request; credentials never leave the server configuration."""
import json
import os
import queue
import threading
import copy
import time
import uuid
import re
from urllib.parse import urlsplit

import httpx

from backend.ai_protocol import Interpretation, PROMPT_VERSION
from backend.service import ServiceError
from scripts.generate_mod import ROOT, no_duplicate_keys


def settings():
    values = {}
    path = ROOT / '.env.local'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"').strip("'")
    return {key: os.environ.get(key, values.get(key, default)) for key, default in
            [('DEEPSEEK_API_KEY', ''), ('DEEPSEEK_MODEL', 'deepseek-flash'),
             ('DEEPSEEK_USE_SYSTEM_PROXY', '0'), ('DASHSCOPE_API_KEY', ''),
             ('BAILIAN_TOKEN_PLAN_API_KEY', ''),
             ('MODEL_PROVIDER', 'deepseek'), ('MODEL_NAME', ''), ('MODEL_BASE_URL', ''),
             ('MODEL_USE_SYSTEM_PROXY', '')]}


def connection(config):
    """Only two explicit providers. Never reuse a different provider's key."""
    provider = config.get('MODEL_PROVIDER', 'deepseek').strip().lower()
    if provider not in ('deepseek', 'bailian'):
        raise ServiceError('model_config_invalid', 'MODEL_PROVIDER只支持bailian或deepseek。', 503)
    bailian = provider == 'bailian'
    model = config.get('MODEL_NAME', '').strip() or ('qwen-plus' if bailian else config['DEEPSEEK_MODEL'])
    base = config.get('MODEL_BASE_URL', '').strip().rstrip('/') or (
        'https://dashscope.aliyuncs.com/compatible-mode/v1' if bailian else 'https://api.deepseek.com')
    url = urlsplit(base)
    host = url.hostname or ''
    if bailian:
        allowed = host in {'dashscope.aliyuncs.com','dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com',
                          'cn-hongkong.dashscope.aliyuncs.com'} or bool(re.fullmatch(
            r'[a-z0-9-]+\.(?:cn-beijing|ap-southeast-1|us-east-1|eu-central-1|ap-northeast-1|cn-hongkong)\.maas\.aliyuncs\.com', host))
        allowed = allowed and url.path == '/compatible-mode/v1'
    else:
        allowed = host == 'api.deepseek.com' and url.path in ('', '/v1')
    if not allowed or url.scheme != 'https' or url.username or url.password or url.query or url.fragment:
        raise ServiceError('model_config_invalid', '模型Base URL须使用所选服务商的官方HTTPS兼容接口地址。', 503)
    try:
        if url.port not in (None,443):
            raise ValueError()
    except ValueError:
        raise ServiceError('model_config_invalid', '模型地址端口无效。', 503) from None
    proxy = config.get('MODEL_USE_SYSTEM_PROXY', '') or ('0' if bailian else config.get('DEEPSEEK_USE_SYSTEM_PROXY','0'))
    key_name = ('BAILIAN_TOKEN_PLAN_API_KEY' if host=='token-plan.cn-beijing.maas.aliyuncs.com'
                else 'DASHSCOPE_API_KEY') if bailian else 'DEEPSEEK_API_KEY'
    return {'provider':provider, 'model':model, 'base_url':base, 'key_name':key_name,
            'api_key':config.get(key_name,''),
            'use_proxy':proxy=='1'}


class ModelClient:
    active_requests = threading.BoundedSemaphore(2)
    total_timeout = 65
    def __init__(self, transport=None):
        self.config = settings()
        self.provider = self.config.get('MODEL_PROVIDER', 'deepseek')
        self.model = self.config.get('MODEL_NAME') or ('qwen-plus' if self.provider=='bailian' else self.config['DEEPSEEK_MODEL'])
        self.transport = transport
        self._caller = threading.local()
        self._worker = threading.local()

    @property
    def diagnostics(self):
        return getattr(self._caller, 'diagnostics', None)

    def parse(self, context):
        started = time.monotonic()
        diagnostic = {'trace_id': str(uuid.uuid4()), 'thinking': 'disabled', 'stages': []}
        diagnostic_lock = threading.Lock()
        self._caller.diagnostics = diagnostic
        def record(stage, **details):
            with diagnostic_lock:
                diagnostic['stages'].append({'stage': stage,
                    'elapsed_ms': round((time.monotonic()-started)*1000), **details})
        def finish(stage, **details):
            record(stage, **details)
            with diagnostic_lock:
                self._caller.diagnostics = copy.deepcopy(diagnostic)
        record('request_started')
        # A socket timeout alone may not bound OS DNS resolution. A daemon watchdog
        # bounds the caller; slots remain occupied until the underlying request ends.
        if not self.active_requests.acquire(blocking=False):
            finish('capacity_rejected')
            raise ServiceError('model_capacity', '模型请求已满，请稍后重试或手动填写。', 429)
        result = queue.Queue(maxsize=1)
        def call():
            self._worker.record = record
            self._worker.started = started
            try:
                result.put((True, self._parse(context)))
            except Exception as exc:
                result.put((False, exc))
            finally:
                self.active_requests.release()
        threading.Thread(target=call, daemon=True, name='model-request').start()
        try:
            ok, value = result.get(timeout=self.total_timeout)
        except queue.Empty:
            finish('total_timeout')
            raise ServiceError('model_timeout', '模型请求超过总等待时间；草稿未改变，可手动填写或稍后重试。', 504) from None
        if not ok:
            finish('failed', error_code=getattr(value, 'code', 'model_internal_error'))
            raise value
        finish('completed')
        return value

    def _parse(self, context):
        record = self._worker.record
        def trace(name, info):
            # HTTP core metadata only. Never serialize info: it may contain headers.
            allowed = ('connect_tcp', 'start_tls', 'send_request_headers', 'send_request_body', 'receive_response_headers')
            if any(part in name for part in allowed):
                record(name)
        if self.transport is None:
            self.config = settings()
        selected = connection(self.config)
        self.provider, self.model = selected['provider'], selected['model']
        record('provider_configured', provider=selected['provider'], model=selected['model'])
        if not selected['api_key']:
            raise ServiceError('model_not_configured', '服务端未配置'+selected['key_name']+'；可以手动填写参数。', 503)
        use_proxy = selected['use_proxy']
        record('network_route', system_proxy=use_proxy)
        try:
            with httpx.Client(timeout=httpx.Timeout(60, connect=10), transport=self.transport,
                              trust_env=use_proxy) as client:
                payload = self.payload(context, selected)
                if selected['provider'] == 'bailian':
                    payload['enable_thinking'] = False
                else:
                    payload['thinking'] = {'type':'disabled'}
                request = client.build_request('POST', selected['base_url']+'/chat/completions',
                    headers={'Authorization':'Bearer '+selected['api_key']}, json=payload)
                request.extensions['trace'] = trace
                response = client.send(request, stream=True)
                try:
                    record('response_headers', http_status=response.status_code)
                    if response.status_code >= 400:
                        raise self.http_error(response.status_code, selected['provider'])
                    chunks = []
                    byte_count = 0
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        if not chunks:
                            record('first_body_chunk')
                        chunks.append(chunk)
                        byte_count += len(chunk)
                        if time.monotonic() - self._worker.started >= self.total_timeout:
                            raise httpx.ReadTimeout('Total response deadline exceeded')
                    response_body = b''.join(chunks)
                    record('body_complete', response_bytes=byte_count)
                finally:
                    response.close()
            data = json.loads(response_body)
            # Some upstream gateways wrap an API error in an HTTP 200 response.
            if isinstance(data, dict) and data.get('error'):
                error = data['error']
                kind = (error.get('code') or error.get('type')) if isinstance(error, dict) else ''
                status = {'service_unavailable_error':503, 'server_error':500,
                          'insufficient_balance':402, 'invalid_api_key':401,
                          'rate_limit_exceeded':429}.get(kind, 502)
                record('upstream_error', mapped_status=status)
                raise self.http_error(status, selected['provider'])
            choice = data['choices'][0]
            if choice.get('finish_reason') != 'stop':
                raise ServiceError('model_incomplete', '模型响应未完整结束；请重试或手动填写。', 502)
            content = choice['message']['content']
            if not content or not content.strip():
                raise ServiceError('model_empty', '模型返回空内容；请重试或手动填写。', 502)
            result = json.loads(content, object_pairs_hook=no_duplicate_keys,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
            return result, data.get('usage')
        except httpx.TimeoutException:
            raise ServiceError('model_timeout', '模型请求超时；草稿未改变，可重试。', 504) from None
        except httpx.RequestError:
            raise ServiceError('model_network_failed', '无法连接模型服务；草稿未改变，可重试或手动填写。', 502) from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ServiceError('model_invalid_output', '模型响应格式无效；草稿未改变，可重试。', 502) from None

    def payload(self, context, selected):
        from backend.player_language import policy
        prompt = (ROOT / 'prompts' / (PROMPT_VERSION + '.md')).read_text(encoding='utf-8')+'\n'+policy()
        return {'model': selected['model'], 'stream': False, 'max_tokens': 2500,
                'response_format': {'type': 'json_object'},
                'messages': [{'role': 'system', 'content': prompt + '\nJSON Schema:\n' + json.dumps(Interpretation.model_json_schema(), ensure_ascii=False)},
                             {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}]}

    @staticmethod
    def http_error(status, provider='deepseek'):
        name = '阿里云百炼' if provider == 'bailian' else 'DeepSeek'
        errors = {
            400: ('model_request_rejected', '模型请求参数被拒绝，请检查模型是否支持JSON输出和当前配置。'),
            404: ('model_unavailable', '模型或接口不存在，请核对百炼地域、业务空间和模型名称。' if provider=='bailian' else '模型或接口不存在，请核对配置。'),
            401: ('model_auth_failed', '模型密钥鉴权失败，请检查服务端配置。'),
            403: ('model_auth_failed', '模型访问被拒绝，请检查服务端权限。'),
            402: ('model_insufficient_balance', '模型账户余额不足，请检查账户。'),
            429: ('model_rate_limited', name+'请求限额已达到，请稍后重试或手动填写。'),
            503: ('model_overloaded', name+'服务当前过于繁忙，暂时无法解析；输入和草稿已保留，可稍后重试或直接填写参数。'),
            500: ('model_upstream_error', name+'服务内部错误，请稍后重试或手动填写。'),
        }
        code, message = errors.get(status, ('model_http_failed', '模型服务请求失败，请稍后重试或手动填写。'))
        return ServiceError(code, message, 503 if status == 503 else 502)
