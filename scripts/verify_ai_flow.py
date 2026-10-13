"""Exercise real packaging and download with either an explicit fixture or real API."""
import argparse
import io
import json
import uuid
import zipfile

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.service import EquipmentService, write_json
from scripts.generate_equipment import FIRST_BLOOD


class FixtureModel:
    model = 'fixture-not-real-api'

    def parse(self, context):
        return {'result': 'suggestion', 'operations': [{'field': 'damage', 'operation': 'set',
                'value': '2d6', 'basis': 'current', 'unit': None}], 'questions': [], 'unsupported': [],
                'explanation': '固定验收响应：基础伤害设为2d6。'}, None


def verify(real=False):
    service = EquipmentService()
    with TestClient(create_app(service, None if real else FixtureModel())) as client:
        def post(path, body):
            response = client.post(path, json=body)
            if response.status_code >= 400:
                raise RuntimeError(str(response.status_code) + ' ' + response.text)
            return response.json()
        state = post('/api/ai/sessions', {'object': FIRST_BLOOD})
        path = '/api/ai/sessions/' + state['session_id']
        state = post(path + '/messages', {'version': 0, 'request_id': str(uuid.uuid4()), 'text': '基础伤害改为2d6'})
        assert state['draft'] == {'damage': '2d6'} and not state['questions'] and not state['unsupported']
        state = post(path + '/preview', {'version': state['version'], 'request_id': str(uuid.uuid4())})
        plan = state['preview']
        # Deliberate test assertion of the user-confirmation gate, not a human user report.
        denied = client.post('/api/plans/' + plan['plan_id'] + '/generate', json={'confirmed': False})
        assert denied.status_code == 409
        generated = post('/api/plans/' + plan['plan_id'] + '/generate', {'confirmed': True, 'accept_experimental': False})
        download = client.get(generated['download_url'])
        assert download.status_code == 200
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            assert archive.testzip() is None and len(archive.namelist()) == 3
        report = {'model_mode': 'real_api' if real else 'fixture', 'session_id': state['session_id'],
                  'plan_id': plan['plan_id'], 'confirmation_gate': 'passed', 'confirmation_actor': 'automated_acceptance_test',
                  'stages': generated['stages'], 'zip_check': generated['zip_check'], 'download': 'passed',
                  'download_bytes': len(download.content), 'game_validation': 'not_performed'}
        output = service.root / ('ai-flow-real.json' if real else 'ai-flow-fixture.json')
        write_json(output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--real', action='store_true', help='Use configured DeepSeek API (incurs usage).')
    verify(parser.parse_args().real)
