import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.service import EquipmentService
from scripts.generate_equipment import FIRST_BLOOD, check_rendered_files, render_files
from scripts.generate_mod import ValidationError


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = EquipmentService(root=Path(self.temp.name))
        self.client = TestClient(create_app(self.service))
        self.addCleanup(self.client.close)
        self.request = {'object': FIRST_BLOOD, 'changes': {'damage': '2d6'}}

    def preview(self, request=None):
        response = self.client.post('/api/previews', json=request or self.request)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def generate(self, plan, **body):
        return self.client.post('/api/plans/' + plan['plan_id'] + '/generate', json={'confirmed': True, **body})

    def fake_generator(self, request, root, **kwargs):
        directory = root / 'test-package'
        directory.mkdir(parents=True)
        pak = directory / 'test.pak'
        pak.write_bytes(b'test-package')
        (directory / '使用说明.txt').write_text('测试说明', encoding='utf-8')
        (directory / 'result.json').write_text(json.dumps({'source_generation': 'passed', 'pak_creation': 'passed',
                'package_check': 'passed', 'game_validation': 'not_performed'}), encoding='utf-8')
        return pak

    def test_catalog_and_scope(self):
        response = self.client.get('/api/equipment', params={'search': '第一滴血'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['items'])
        detail = self.client.get('/api/equipment/' + FIRST_BLOOD).json()
        self.assertIn('damage', detail['field_rules'])
        self.assertNotIn('cast_distance_m', detail['field_rules'])
        self.assertEqual(self.client.get('/api/equipment', params={'limit': 101}).status_code, 422)

    def test_reject_unknown_skill_fields_and_bad_types(self):
        cases = [{'object': 'healing_word', 'changes': {'cast_distance_m': 36}},
                 {'object': FIRST_BLOOD, 'changes': {'dexterity_bonus': 2}},
                 {'object': FIRST_BLOOD, 'changes': {}},
                 {'object': FIRST_BLOOD, 'changes': {'damage': '99d6'}},
                 {'object': FIRST_BLOOD, 'changes': {'weight_kg': True}},
                 {'object': FIRST_BLOOD, 'changes': {'weight_kg': '1'}},
                 {'object': FIRST_BLOOD, 'changes': {'weight_kg': -1}},
                 {**self.request, 'confirmed': True}]
        for request in cases:
            with self.subTest(request=request):
                self.assertEqual(self.client.post('/api/previews', json=request).status_code, 422)

    def test_duplicate_keys_and_nonfinite_json(self):
        for body in ['{"object":"a","object":"b","changes":{}}',
                     '{"object":"a","changes":{"weight_kg":NaN}}', 'broken']:
            self.assertEqual(self.client.post('/api/previews', content=body,
                            headers={'content-type': 'application/json'}).status_code, 422)

    def test_preview_preserves_original_and_does_not_generate(self):
        plan = self.preview()
        self.assertEqual(plan['changes'][0]['original'], '1d6')
        self.assertEqual(plan['game_validation'], 'not_performed')
        self.assertFalse((self.service.root / 'packages').exists())

    def test_confirmation_and_no_parameter_injection(self):
        plan = self.preview()
        self.assertEqual(self.generate(plan, confirmed=False).status_code, 409)
        self.assertEqual(self.generate(plan, confirmed='true').status_code, 422)
        self.assertEqual(self.generate(plan, changes={'damage': '3d6'}).status_code, 422)
        self.assertEqual(self.client.get('/api/plans/' + plan['plan_id'] + '/download').status_code, 409)

    def test_experimental_gate(self):
        plan = self.preview({'object': FIRST_BLOOD, 'changes': {'damage': '3d6'}})
        self.assertTrue(plan['experimental'])
        self.assertEqual(self.generate(plan).json()['detail']['code'], 'experimental_confirmation_required')
        with patch('backend.service.generate', side_effect=self.fake_generator):
            self.assertEqual(self.generate(plan, accept_experimental=True).status_code, 200)

    def test_changed_versions_require_new_preview(self):
        plan = self.preview()
        with patch.object(self.service, 'versions', return_value={'changed': True}):
            self.assertEqual(self.generate(plan).json()['detail']['code'], 'stale_preview')

    def test_complete_flow_download_idempotency_and_persistence(self):
        plan = self.preview()
        with patch('backend.service.generate', side_effect=self.fake_generator) as generator:
            result = self.generate(plan)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(self.generate(plan).status_code, 200)
            self.assertEqual(generator.call_count, 1)
        response = self.client.get(result.json()['download_url'])
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read('修改清单.json'))
            self.assertEqual(manifest['confirmed_request'], self.request)
            self.assertEqual(manifest['game_validation'], 'not_performed')
        other = EquipmentService(root=self.service.root)
        self.assertEqual(other.read(plan['plan_id'])['status'], 'succeeded')
        other.download(plan['plan_id']).write_bytes(b'corrupted')
        self.assertEqual(self.client.get(result.json()['download_url']).status_code, 500)

    def test_failure_has_no_download_and_is_recorded(self):
        plan = self.preview()
        with patch('backend.service.generate', side_effect=RuntimeError('packaging failure')):
            self.assertEqual(self.generate(plan).status_code, 500)
        status = self.client.get('/api/plans/' + plan['plan_id']).json()
        self.assertEqual(status['status'], 'failed')
        self.assertNotIn('error', status)
        self.assertEqual(self.generate(plan).status_code, 409)
        self.assertEqual(self.client.get('/api/plans/' + plan['plan_id'] + '/download').status_code, 409)

    def test_unknown_plan_and_traversal(self):
        self.assertEqual(self.client.get('/api/plans/not-a-uuid').status_code, 404)

    def test_output_check_rejects_unrequested_field(self):
        catalog = self.service.catalog()
        files = render_files(self.request, '00000000-0000-4000-8000-000000000001', catalog=catalog)
        path = next(p for p in files if p.suffix == '.txt')
        files[path] += b'data "DefaultBoosts" "bad"\n'
        with self.assertRaises(ValidationError):
            check_rendered_files(self.request, '00000000-0000-4000-8000-000000000001', files, catalog=catalog)

    def test_name_and_weight_checks(self):
        catalog = self.service.catalog()
        request = {'object': FIRST_BLOOD, 'changes': {'name': '晨光<&短剑', 'weight_kg': 1.125}}
        identifier = '00000000-0000-4000-8000-000000000001'
        files = render_files(request, identifier, catalog=catalog)
        check_rendered_files(request, identifier, files, catalog=catalog)
        path = next(p for p in files if p.suffix == '.xml')
        files[path] = files[path].replace('晨光'.encode(), '错误'.encode())
        with self.assertRaises(ValidationError):
            check_rendered_files(request, identifier, files, catalog=catalog)


if __name__ == '__main__':
    unittest.main()
