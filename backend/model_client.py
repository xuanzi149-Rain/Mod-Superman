"""One bounded model request; credentials never leave the server configuration."""
import json
import os

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
            [('DEEPSEEK_API_KEY', ''), ('DEEPSEEK_MODEL', 'deepseek-flash')]}


class ModelClient:
    def __init__(self, transport=None):
        self.config = settings()
        self.model = self.config['DEEPSEEK_MODEL']
        self.transport = transport

    def parse(self, context):
        if self.transport is None:
            self.config = settings()
            self.model = self.config['DEEPSEEK_MODEL']
        if not self.config['DEEPSEEK_API_KEY']:
            raise ServiceError('model_not_configured', '服务端未配置模型密钥；可以手动填写参数。', 503)
        prompt = (ROOT / 'prompts' / (PROMPT_VERSION + '.md')).read_text(encoding='utf-8')
        try:
            with httpx.Client(timeout=60, transport=self.transport) as client:
                response = client.post('https://api.deepseek.com/chat/completions',
                    headers={'Authorization': 'Bearer ' + self.config['DEEPSEEK_API_KEY']},
                    json={'model': self.model, 'stream': False, 'max_tokens': 2500,
                          'response_format': {'type': 'json_object'},
                          'messages': [{'role': 'system', 'content': prompt + '\nJSON Schema:\n' + json.dumps(Interpretation.model_json_schema(), ensure_ascii=False)},
                                       {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}]})
            if response.status_code >= 400:
                code = {401: 'model_auth_failed', 403: 'model_auth_failed', 429: 'model_rate_limited'}.get(response.status_code, 'model_http_failed')
                raise ServiceError(code, '模型请求失败（HTTP %s）；保留草稿，可重试或手动填写。' % response.status_code, 502)
            data = response.json()
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
