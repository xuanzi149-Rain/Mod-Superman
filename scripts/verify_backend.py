"""Run real API -> LSLib -> ZIP checks without installing any Mod."""
import io
import json
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient
from backend.app import app
from scripts.generate_equipment import FIRST_BLOOD
from scripts.generate_mod import ROOT


def main():
    reports = []
    with TestClient(app) as client:
        for changes in ({'damage': '2d6'}, {'name': '后端测试<&短剑', 'weight_kg': 1.125, 'rarity': 'Rare'}):
            request = {'object': FIRST_BLOOD, 'changes': changes}
            preview = client.post('/api/previews', json=request)
            preview.raise_for_status()
            plan = preview.json()
            generated = client.post('/api/plans/' + plan['plan_id'] + '/generate',
                                    json={'confirmed': True, 'accept_experimental': plan['experimental']})
            generated.raise_for_status()
            result = generated.json()
            assert result['status'] == 'succeeded', result
            download = client.get(result['download_url'])
            download.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                assert archive.testzip() is None
                manifest = json.loads(archive.read('修改清单.json'))
                assert manifest['confirmed_request'] == request
                assert manifest['package_check'] == 'passed'
                assert manifest['game_validation'] == 'not_performed'
            reports.append({'plan_id': plan['plan_id'], 'request': request, 'stages': result['stages'],
                            'zip_check': result['zip_check'], 'zip_sha256': result['zip_sha256'],
                            'download_file': str(app.state.service.download(plan['plan_id']))})
    path = ROOT / 'build/backend/verification.json'
    path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
