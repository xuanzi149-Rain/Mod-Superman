import tempfile
import unittest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.service import EquipmentService
from backend.equipment_presentation import presentation


class PresentationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.service = EquipmentService(root=directory.name)
        self.client = TestClient(create_app(self.service))
        self.addCleanup(self.client.close)

    def test_silver_pendant_only_guidance_selectable(self):
        raw = self.client.get('/api/equipment', params={'search': '白银坠饰'}).json()
        self.assertEqual(raw['total'], 3)
        visible = self.client.get('/api/equipment', params={
            'search': '白银坠饰', 'player_available_only': True}).json()
        self.assertEqual(visible['total'], 1)
        self.assertEqual(visible['items'][0]['object_id'], 'equipment:8b5fb90f-f957-4a1a-b8eb-2baff0c3b40b')
        self.assertIn('神导术', visible['items'][0]['presentation']['effect'])
        for item in raw['items']:
            if item['object_id'] != visible['items'][0]['object_id']:
                self.assertIn('普通首饰', item['presentation']['kind'])
                self.assertEqual(item['presentation']['availability'], 'unverified')

    def test_ordinary_jewelry_still_available_and_original_unchanged(self):
        visible = self.client.get('/api/equipment', params={
            'search': '白银护符', 'player_available_only': True}).json()
        self.assertEqual(visible['total'], 1)
        item = visible['items'][0]
        self.assertEqual(item['presentation']['kind'], '普通首饰')
        self.assertEqual(item['presentation']['effect'], '无固有魔法效果')
        detail = self.service.detail(item['object_id'])
        self.assertIsNone(detail['original']['Rarity'])
        self.assertEqual(detail['game_validation'], self.service.catalog()['items'][item['object_id']]['game_validation'])

    def test_evidence_requires_exact_object_and_record(self):
        catalog = self.service.catalog()['items']
        known = catalog['equipment:8b5fb90f-f957-4a1a-b8eb-2baff0c3b40b']
        self.assertEqual(presentation({**known, 'record': 'changed'})['availability'], 'unverified')
        self.assertEqual(presentation({**known, 'root_uuid': 'other'})['availability'], 'unverified')
        self.assertEqual(sum(presentation(i)['availability'] == 'verified' for i in catalog.values()), 5)


if __name__ == '__main__':
    unittest.main()
