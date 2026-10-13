"""Explicit real API evaluation; never runs as part of unit tests."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import uuid

from backend.ai_service import AIService
from backend.ai_protocol import PROMPT_VERSION
from backend.service import EquipmentService, ServiceError, write_json
from scripts.generate_equipment import FIRST_BLOOD
from scripts.generate_mod import ROOT


def evaluate(split):
    cases_path = ROOT / 'data/ai_cases.json'
    cases = json.loads(cases_path.read_text(encoding='utf-8'))
    service = EquipmentService()
    ai = AIService(service)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    path = service.root / 'ai_evaluations' / (run_id + '-' + split + '.json')
    report = {'run_id': run_id, 'split': split, 'model': ai.model.model, 'prompt_version': PROMPT_VERSION,
              'prompt_sha256': hashlib.sha256((ROOT / 'prompts' / (PROMPT_VERSION + '.md')).read_bytes()).hexdigest(),
              'cases_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(), 'results': []}
    for case in cases:
        if case['split'] != split:
            continue
        state = ai.create(FIRST_BLOOD)
        original = Decimal(str(state['detail']['original']['Weight']))
        error = None
        for text in case['turns']:
            try:
                state = ai.message(state['session_id'], {'version': state['version'], 'request_id': str(uuid.uuid4()), 'text': text})
            except ServiceError as exc:
                error = exc.code
                state = ai.get(state['session_id'])
                break
        passed = error == case.get('error')
        if not error:
            if 'status' in case:
                passed &= state['status'] == case['status']
            else:
                passed &= state['status'] == 'suggestion' and not state['questions']
            expected = dict(case.get('expected', {}))
            if 'weight_factor' in case:
                expected['weight_kg'] = float(original * Decimal(str(case['weight_factor'])))
            if 'weight_add' in case:
                expected['weight_kg'] = float(original + Decimal(str(case['weight_add'])))
            if expected:
                # Reject unintended extra modifications, not only missing expected values.
                passed &= state['draft'] == expected
            passed &= all(field not in state['draft'] for field in case.get('absent', []))
            passed &= bool(state['unsupported']) == case.get('unsupported', case.get('status') == 'unsupported')
            if case.get('status') in ('clarify', 'unsupported'):
                passed &= not state['draft']
        row = {'id': case['id'], 'passed': bool(passed), 'error': error,
               'session_id': state['session_id'], 'status': state['status'], 'draft': state['draft'],
               'questions': state['questions'], 'unsupported': state['unsupported'], 'history': state['history']}
        report['results'].append(row)
        report['passed'] = sum(r['passed'] for r in report['results'])
        report['total'] = len(report['results'])
        write_json(path, report)
        print(case['id'], 'PASS' if passed else 'FAIL', error or state['status'], flush=True)
        if error in ('model_not_configured', 'model_auth_failed', 'model_network_failed'):
            report['stopped'] = error
            write_json(path, report)
            break
    print(json.dumps({'report': str(path), 'passed': report.get('passed', 0), 'total': report.get('total', 0)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['development', 'holdout'], required=True)
    evaluate(parser.parse_args().split)
