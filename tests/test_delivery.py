import json
import tempfile
import threading
import time
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.service import EquipmentService, write_json
from backend.jobs import Jobs
from backend.maintenance import maintain
from backend.model_client import ModelClient
from backend.service import ServiceError
from scripts.generate_equipment import FIRST_BLOOD


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = EquipmentService(root=Path(self.temp.name))
        self.app = create_app(self.service)
        self.addCleanup(self.app.state.jobs.close)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def preview(self):
        r = self.client.post('/api/previews', json={'object': FIRST_BLOOD, 'changes': {'damage': '2d6'}})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def fake(self, request, root, **kwargs):
        directory = root / str(uuid.uuid4())
        directory.mkdir(parents=True)
        pak = directory / 'test.pak'
        pak.write_bytes(b'test-pak-not-real')
        (directory / '使用说明.txt').write_text('固定说明', encoding='utf-8')
        (directory / 'result.json').write_text(json.dumps(dict(source_generation='passed', pak_creation='passed',
            package_check='passed', game_validation='not_performed')), encoding='utf-8')
        return pak

    def wait(self, plan):
        for _ in range(100):
            result = self.client.get('/api/plans/'+plan['plan_id']).json()
            if result['status'] not in ('queued', 'generating'):
                return result
            time.sleep(.02)
        self.fail('Task did not finish')

    def test_background_generation_does_not_lock_state_and_deduplicates(self):
        plan = self.preview()
        started, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            started.set()
            release.wait(5)
            return self.fake(*args, **kwargs)
        url = '/api/plans/'+plan['plan_id']
        with patch('backend.service.generate', side_effect=slow) as generator:
            try:
                self.assertEqual(self.client.post(url+'/tasks', json={'confirmed':True}).status_code,202)
                self.assertTrue(started.wait(2))
                self.assertEqual(self.client.get(url).json()['status'],'generating')
                self.assertEqual(self.client.post(url+'/tasks',json={'confirmed':True}).status_code,202)
                self.assertEqual(self.client.post('/api/ai/sessions',json={'object':FIRST_BLOOD}).status_code,201)
            finally:
                release.set()
            self.assertEqual(self.wait(plan)['status'],'succeeded')
            self.assertEqual(generator.call_count,1)

    def test_ownership_applies_to_session_plan_download_and_feedback(self):
        plan = self.preview()
        session = self.client.post('/api/ai/sessions',json={'object':FIRST_BLOOD}).json()
        with TestClient(self.app) as stranger:
            for url in ['/api/ai/sessions/'+session['session_id'], '/api/plans/'+plan['plan_id'],
                        '/api/plans/'+plan['plan_id']+'/download']:
                self.assertEqual(stranger.get(url).status_code,404)
            self.assertEqual(stranger.post('/api/plans/'+plan['plan_id']+'/feedback',json={}).status_code,404)
        self.assertEqual(self.client.get('/api/ai/sessions/'+session['session_id']).status_code,200)

    def test_sqlite_restores_without_json_and_events_are_unique(self):
        plan = self.preview()
        path = self.service.path(plan['plan_id'])
        write_json(path,plan)
        path.unlink()
        self.assertEqual(EquipmentService(root=self.service.root).read(plan['plan_id']),plan)
        with self.service.store.connect() as db:
            count=db.execute('SELECT count(*) FROM events WHERE plan_id=?',(plan['plan_id'],)).fetchone()[0]
        self.assertEqual(count,1)

    def test_feedback_deduplicates_conflicts_and_never_upgrades_game_validation(self):
        plan = self.preview();url='/api/plans/'+plan['plan_id']
        body=dict(request_id='feedback-one', outcome='success', stage='game_effect', game_version='', detail='')
        self.assertEqual(self.client.post(url+'/feedback',json=body).status_code,409)
        with patch('backend.service.generate',side_effect=self.fake):
            self.client.post(url+'/tasks',json={'confirmed':True})
            self.assertEqual(self.wait(plan)['status'],'succeeded')
        for _ in range(2):
            self.assertEqual(self.client.post(url+'/feedback',json=body).status_code,200)
        self.assertEqual(self.client.post(url+'/feedback',json={**body,'detail':'changed'}).status_code,409)
        self.assertEqual(self.client.get(url).json()['game_validation'],'not_performed')
        with self.service.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM feedback').fetchone()[0],1)
        text=self.client.get(url+'/instructions').json()['text']
        self.assertIn('不需要再次本地打包',text)
        self.assertIn('基础伤害：1d6 → 2d6',text)

    def test_failure_and_restart_recovery_have_no_download(self):
        plan = self.preview();url='/api/plans/'+plan['plan_id']
        with patch('backend.service.generate',side_effect=RuntimeError('private diagnostic')):
            self.client.post(url+'/tasks',json={'confirmed':True})
            self.assertEqual(self.wait(plan)['status'],'failed')
        self.assertEqual(self.client.get(url+'/download').status_code,409)
        self.assertNotIn('private diagnostic',self.client.get(url).text)
        self.app.state.jobs.close()  # A restart means the predecessor has fully stopped.
        plan['status']='queued';write_json(self.service.path(plan['plan_id']),plan)
        self.service.path(plan['plan_id']).unlink()
        jobs=Jobs(self.service)
        try:self.assertEqual(self.service.read(plan['plan_id'])['status'],'interrupted')
        finally:jobs.close()

    def test_expired_artifacts_cleanup_preserves_records_and_backup(self):
        plan=self.preview();url='/api/plans/'+plan['plan_id']
        with patch('backend.service.generate',side_effect=self.fake):
            self.client.post(url+'/tasks',json={'confirmed':True});plan=self.wait(plan)
        plan['generated_at']=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
        write_json(self.service.path(plan['plan_id']),plan)
        self.assertEqual(self.client.get(url+'/download').status_code,410)
        maintain(self.service)
        self.assertFalse((self.service.root/'downloads'/(plan['plan_id']+'.zip')).exists())
        self.assertEqual(self.service.read(plan['plan_id'])['status'],'succeeded')
        self.assertTrue(list((self.service.root/'backups').glob('*.sqlite3')))

    def test_origin_size_and_rate_limits(self):
        self.assertEqual(self.client.post('/api/previews',json={},headers={'Origin':'https://foreign.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/previews',json={'long':'x'*25000}).status_code,413)
        session=self.client.post('/api/ai/sessions',json={'object':FIRST_BLOOD}).json()
        for _ in range(10):
            self.client.post('/api/ai/sessions/'+session['session_id']+'/messages',json={})
        self.assertEqual(self.client.post('/api/ai/sessions/'+session['session_id']+'/messages',json={}).status_code,429)

    def test_task_rejects_unconfirmed_experimental_and_stale_previews(self):
        plan=self.preview();url='/api/plans/'+plan['plan_id']+'/tasks'
        self.assertEqual(self.client.post(url,json={'confirmed':False}).status_code,409)
        plan['experimental']=True;write_json(self.service.path(plan['plan_id']),plan)
        self.assertEqual(self.client.post(url,json={'confirmed':True}).status_code,409)
        with patch.object(self.service,'versions',return_value={'changed':True}):
            self.assertEqual(self.client.post(url,json={'confirmed':True,'accept_experimental':True}).status_code,409)

    def test_total_model_timeout_bounds_dns_wait_and_releases_capacity(self):
        client=ModelClient();client.total_timeout=.01
        entered,release=threading.Event(),threading.Event()
        def stalled(context):
            entered.set();release.wait(2);return {},None
        with patch.object(client,'_parse',side_effect=stalled):
            try:
                with self.assertRaises(ServiceError) as caught:client.parse({})
                self.assertEqual(caught.exception.code,'model_timeout')
                self.assertTrue(entered.is_set())
            finally:release.set()

    def test_capacity_and_stale_ai_plan_do_not_dispatch(self):
        plan=self.preview();url='/api/plans/'+plan['plan_id']+'/tasks'
        slots=self.app.state.jobs.slots
        for _ in range(3):slots.acquire()
        try:self.assertEqual(self.client.post(url,json={'confirmed':True}).status_code,429)
        finally:
            for _ in range(3):slots.release()
        state=self.client.post('/api/ai/sessions',json={'object':FIRST_BLOOD}).json()
        base='/api/ai/sessions/'+state['session_id']
        self.client.post(base+'/draft',json={'version':0,'request_id':'manual','changes':{'damage':'2d6'}})
        state=self.client.post(base+'/preview',json={'version':1,'request_id':'preview'}).json()
        self.client.post(base+'/draft',json={'version':1,'request_id':'change','changes':{'damage':'3d6'}})
        r=self.client.post('/api/plans/'+state['preview']['plan_id']+'/tasks',json={'confirmed':True})
        self.assertEqual(r.status_code,409)
        self.assertEqual(r.json()['detail']['code'],'stale_ai_preview')


if __name__=='__main__':unittest.main()
