import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.service import EquipmentService, ServiceError
from backend.workflow_v11 import CraftService
from scripts.crafting_compiler_v11 import load_resources
from scripts.generate_mod import ROOT


class FixedModel:
    model='fixed-response-not-live-model';provider='test'
    def run(self,task,c):
        if task=='review':
            return dict(schema_version='review-v1',**c['request'],plan_digest=c['plan_digest'],items=[dict(text_id=t['id'],source_text_digest=t['source_text_digest'],source_status='consistent',findings=[],proposed_text=None,proposal_status='not_requested',proposal_findings=[]) for t in c['texts']]),{'prompt_tokens':1,'completion_tokens':1}
        op=dict(id='op1',requirement_ids=['r1'],group_id='g1',kind='set_parameter',target='rarity',payload={'value':'Rare','unit':None})
        return dict(schema_version='parse-v1',**c['request'],intent_summary='只修改稀有度',requirements=[dict(id='r1',quote=c['latest_message']['text'],meaning='稀有度',operation_ids=['op1'],issue_ids=[],text_request_ids=[],issue_update_ids=[],no_change=False)],operations=[op],issues=[],text_requests=[],issue_updates=[]),{'prompt_tokens':1,'completion_tokens':1}


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources=load_resources()
        cls.fixtures=json.loads((ROOT/'data/v1.1/phase-b-cases.json').read_text(encoding='utf-8'))
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.service=EquipmentService(root=Path(self.tmp.name));self.app=create_app(self.service,craft_model=FixedModel())
        self.addCleanup(self.app.state.jobs.close)
        self.client=TestClient(self.app);self.addCleanup(self.client.close)
        self.patch=patch('backend.workflow_v11.load_resources',return_value=self.resources);self.patch.start();self.addCleanup(self.patch.stop)
    def create(self,mode='modify_existing',fixture='create_weapon'):
        r=self.client.post('/api/v11/sessions',json={'mode':mode,'base_equipment':self.fixtures[fixture]['base_equipment'],'inheritance':'retain_base'})
        self.assertEqual(r.status_code,201,r.text);return r.json()
    def act(self,s,action,data=None,**kwargs):
        r=self.client.post('/api/v11/sessions/'+s['session_id']+'/'+action,json={'revision':s['revision'],'request_id':str(uuid.uuid4()),'data':data or {},**kwargs})
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def edit(self,s,kind,target,payload):
        return self.act(s,'edit',{'operations':[{'kind':kind,'target':target,'payload':payload,'group_id':'g'}]})
    def test_delete_draft_is_owned_persistent_and_preserves_delivery(self):
        s=self.create();ident=s['session_id'];url='/api/v11/sessions/'+ident+'/delete'
        with TestClient(self.app) as other:
            self.assertEqual(other.post(url,json={}).status_code,404)
        task_id=str(uuid.uuid4())
        self.service.store.snapshot('v11_tasks',task_id,{'session_id':ident,'status':'generating','plan':s['plan']})
        self.assertEqual(self.client.post(url,json={}).status_code,409)
        self.service.store.snapshot('v11_tasks',task_id,{'session_id':ident,'status':'succeeded','plan':s['plan']})
        self.assertEqual(self.client.post(url,json={}).status_code,200)
        self.assertEqual(self.client.post(url,json={}).status_code,200)
        self.assertFalse(any(x['kind']=='v11_sessions' and x['id']==ident for x in self.client.get('/api/v11/history').json()['items']))
        self.assertEqual(self.service.store.get('v11_tasks',task_id)['status'],'succeeded')
        restored=CraftService(self.service,self.app.state.jobs,FixedModel())
        self.assertIsNotNone(restored.view(ident))

    def test_manual_model_ownership_dedup_and_stale_revision(self):
        s=self.create();before=s
        self.assertFalse(s['has_parsed'])
        s=self.act(s,'message',{'text':'只改稀有度为稀有'})
        self.assertTrue(s['has_parsed'])
        restored=CraftService(self.service,self.app.state.jobs,FixedModel()).view(s['session_id'])
        self.assertTrue(restored['has_parsed'])
        self.assertEqual(s['plan']['parameters']['rarity'],'Rare');self.assertTrue(s['ready'])
        body={'revision':s['revision'],'request_id':str(uuid.uuid4()),'data':{'operations':[dict(kind='set_parameter',target='weight_kg',payload={'value':1.5},group_id='g')]}}
        url='/api/v11/sessions/'+s['session_id']+'/edit'
        first=self.client.post(url,json=body);second=self.client.post(url,json=body)
        self.assertEqual(first.json()['revision'],second.json()['revision'])
        self.assertEqual(self.client.post(url,json={**body,'request_id':str(uuid.uuid4()),'revision':before['revision']}).status_code,409)
        with TestClient(self.app) as other:self.assertEqual(other.get('/api/v11/sessions/'+s['session_id']).status_code,404)
    def test_remove_result_preserves_other_changes(self):
        s=self.create()
        s=self.edit(s,'set_parameter','weight_kg',{'value':0})
        s=self.act(s,'edit',{'texts':[dict(target={'owner':'equipment','field':'name'},mode='exact',text='Fool',style=None)]})
        self.assertEqual(s['plan']['parameters']['weight_kg'],0)
        s=self.act(s,'edit',{'texts':[dict(target={'owner':'equipment','field':'name'},mode='reset',text=None,style=None)]})
        self.assertFalse(s['texts']);self.assertIsNone(s['plan']['display']['name'])
        self.assertEqual(s['plan']['parameters']['weight_kg'],0)
        s=self.act(s,'edit',{'texts':[dict(target={'owner':'equipment','field':'name'},mode='exact',text='Fool',style=None)]})
        s=self.act(s,'review')
        self.assertEqual(s['plan']['display']['name'],'Fool')
        s=self.edit(s,'restore_parameter','weight_kg',{})
        self.assertIsNone(s['plan']['parameters']['weight_kg'])
        self.assertEqual(s['plan']['display']['name'],'Fool')
        restored=CraftService(self.service,self.app.state.jobs,FixedModel()).view(s['session_id'])
        self.assertIsNone(restored['plan']['parameters']['weight_kg'])

    def test_free_text_and_legacy_pending_restore_without_review(self):
        s=self.create()
        s=self.act(s,'edit',{'texts':[dict(target={'owner':'equipment','field':'name'},mode='exact',text='测试名称',style=None)]})
        self.assertFalse(s['texts']);self.assertEqual(s['plan']['display']['name'],'测试名称')
        craft=self.app.state.craft;session=craft.get(s['session_id'])
        session.texts={'equipment:description':dict(id='equipment:description',target={'owner':'equipment','field':'description'},mode='exact',text='传说能摧毁世界',style=None)}
        session.latest_review={'output':{'items':[{'source_status':'conflict'}]}}
        craft.save(s['session_id'],session)
        fresh=CraftService(self.service,self.app.state.jobs,FixedModel())
        with patch.object(fresh.model,'run',side_effect=AssertionError('No text review call')):
            restored=fresh.view(s['session_id'])
            self.assertFalse(restored['texts']);self.assertTrue(restored['ready']);self.assertIsNone(restored['review'])
            self.assertEqual(restored['plan']['display']['description'],'传说能摧毁世界')
            self.assertFalse(fresh.get(s['session_id']).preview()['issues'])

    def test_restart_drops_legacy_failed_requirement_but_keeps_adopted_plan(self):
        s=self.create();s=self.edit(s,'set_parameter','rarity',{'value':'Rare'})
        craft=self.app.state.craft;session=craft.get(s['session_id'])
        session.issues['old']={'id':'old','kind':'clarification','detail':'需要状态ID','question':'请提供沉睡状态的系统ID','options':[],'requirement_ids':['r1']}
        craft.save(s['session_id'],session)
        fresh=CraftService(self.service,self.app.state.jobs,FixedModel())
        restored=fresh.get(s['session_id'])
        self.assertNotIn('old',restored.issues)
        self.assertFalse(restored.draft.plan.unresolved)
        self.assertEqual(restored.draft.plan.parameters.rarity,'Rare')
        self.assertTrue(fresh.view(s['session_id'])['ready'])

    def test_parse_error_returns_reason_and_preserves_draft(self):
        s=self.create();session=self.app.state.craft.get(s['session_id'])
        with patch.object(session,'submit',side_effect=ValueError('invalid_issue_resolution')):
            response=self.client.post('/api/v11/sessions/'+s['session_id']+'/message',json={
                'revision':s['revision'],'request_id':str(uuid.uuid4()),'data':{'text':'命中施加一回合震慑'}})
        self.assertEqual(response.status_code,422)
        self.assertIn('旧问题处理记录',response.json()['detail']['message'])
        self.assertNotIn('invalid_issue_resolution',response.text)
        restored=self.client.get('/api/v11/sessions/'+s['session_id']).json()
        self.assertEqual(restored['revision'],s['revision'])
        self.assertEqual(restored['plan'],s['plan'])
        self.assertEqual(session.last_error['details'],'invalid_issue_resolution')
        self.assertNotIn('details',restored['last_error'])
    def test_invalid_edit_preserves_requirement_until_explicit_withdrawal(self):
        s=self.create();s=self.edit(s,'set_parameter','armor_class',{'value':20})
        self.assertIsNone(s['plan']['parameters']['armor_class']);self.assertTrue(s['issues'])
        s=self.act(s,'edit',{'withdraw':[s['issues'][0]['id']],'quote':'撤回这项要求'})
        self.assertFalse(s['issues'])
    def test_withdraw_failed_request_can_preview_previous_changes(self):
        s=self.create();s=self.act(s,'message',{'text':'只改稀有度为稀有'})
        session=self.app.state.craft.get(s['session_id'])
        session.issues['failed-request']={'id':'failed-request','kind':'clarification','detail':'后续要求未通过检查'}
        session.draft.plan.unresolved=['后续要求未通过检查']
        self.app.state.craft.save(s['session_id'],session)
        blocked=self.client.post('/api/v11/sessions/'+s['session_id']+'/preview',json={'revision':s['revision'],'request_id':str(uuid.uuid4()),'data':{}})
        self.assertEqual(blocked.status_code,422)
        s=self.act(s,'edit',{'withdraw':['failed-request'],'quote':'放弃这些未完成要求，仅核对已采用修改'})
        self.assertFalse(s['issues']);self.assertEqual(s['plan']['parameters']['rarity'],'Rare')
        s=self.act(s,'preview');self.assertTrue(s['ready'])

    def test_followup_keeps_original_request_and_hides_internal_error(self):
        s=self.create();session=self.app.state.craft.get(s['session_id'])
        issue={'id':'aura','kind':'clarification','detail':'伤害还是命中？'}
        session.issues['aura']=issue
        session.history.append({'user':'装备后周围5m的队友攻击获得1d4加成','feedback':{'unresolved':[issue]},'answers':[]})
        c=session.context('1d4作用于攻击伤害，是自动生效','followup-test',answers=['aura'])
        linked=c['followup_context']['linked_issues'][0]
        self.assertIn('周围5m的队友',linked['original_messages'][0])
        self.assertEqual(c['followup_context']['answer'],'1d4作用于攻击伤害，是自动生效')
        session.issues['bad']={'id':'bad','kind':'capability_gap','detail':'1 validation error for Plan input_type=dict errors.pydantic.dev'}
        view=self.app.state.craft.view(s['session_id'])
        self.assertNotIn('pydantic',str(view['issues']))
        self.assertIn('pydantic',session.issues['bad']['detail'])

    def test_failed_input_is_transient_and_does_not_block_existing_plan(self):
        from backend.task8_protocol import recovery_issue
        s=self.create();s=self.act(s,'message',{'text':'只改稀有度为稀有'})
        craft=self.app.state.craft;session=craft.get(s['session_id'])
        before=self.service.store.get('v11_sessions',s['session_id'])
        rejected='这是一条不能解析的测试输入'
        with patch.object(session.model,'run',side_effect=lambda task,c:(recovery_issue(c),{})):
            response=self.act(s,'message',{'text':rejected})
        self.assertTrue(response['input_retained']);self.assertTrue(response['input_feedback'])
        self.assertEqual(response['revision'],s['revision'])
        self.assertEqual(response['plan'],s['plan']);self.assertFalse(response['issues'])
        after=self.service.store.get('v11_sessions',s['session_id'])
        self.assertEqual(before,after);self.assertNotIn(rejected,json.dumps(after,ensure_ascii=False))
        self.assertFalse(session.log)
        preview=self.act(response,'preview');self.assertTrue(preview['ready'])

    def test_schema_and_native_catalog(self):
        self.assertIn('plan',self.client.get('/api/v11/schema').json())
        rows=self.client.get('/api/v11/catalog?kind=PassiveData&search=平衡').json()['items']
        self.assertTrue(any(x['id']=='ARM_Balance_1_Passive' for x in rows))
    def test_restart_marks_pending_tasks_interrupted(self):
        ident=str(uuid.uuid4());self.service.store.snapshot('v11_tasks',ident,{'status':'queued','task_id':ident})
        c=CraftService(self.service,self.app.state.jobs,FixedModel())
        self.assertEqual(c.task(ident)['failure_stage'],'service_restart')
    def test_history_is_owned_and_model_failure_can_retry(self):
        s=self.create()
        rows=self.client.get('/api/v11/history').json()['items']
        self.assertIn(s['session_id'],[r['id'] for r in rows])
        with TestClient(self.app) as other:
            self.assertEqual(other.get('/api/v11/history').json()['items'],[])
        model=self.app.state.craft.get(s['session_id']).model
        with patch.object(model,'run',side_effect=ValueError('simulated timeout')):
            r=self.client.post('/api/v11/sessions/'+s['session_id']+'/message',json={'revision':s['revision'],'request_id':str(uuid.uuid4()),'data':{'text':'稀有度改成稀有'}})
            self.assertIn(r.status_code,(200,422))
        current=self.client.get('/api/v11/sessions/'+s['session_id']).json()
        self.assertEqual(current['plan'],s['plan'])
        current=self.act(current,'message',{'text':'稀有度改成稀有'})
        self.assertEqual(current['plan']['parameters']['rarity'],'Rare')

    def test_busy_and_source_change_are_rejected(self):
        s=self.create();runtime=self.app.state.craft.get(s['session_id'])
        import threading
        ready=threading.Event();release=threading.Event()
        def hold():
            with runtime.lock:ready.set();release.wait(5)
        t=threading.Thread(target=hold);t.start();ready.wait(5)
        try:
            r=self.client.post('/api/v11/sessions/'+s['session_id']+'/preview',json={'revision':s['revision'],'request_id':str(uuid.uuid4()),'data':{}})
            self.assertEqual(r.status_code,409)
        finally:release.set();t.join()
        s=self.edit(s,'set_parameter','rarity',{'value':'Rare'});s=self.act(s,'preview')
        with patch('backend.workflow_v11.load_resources',return_value={}):
            r=self.client.post('/api/v11/sessions/'+s['session_id']+'/generate',json={'revision':s['revision'],'request_id':str(uuid.uuid4()),'data':{'digest':s['digest'],'confirmed':True,'accept_experimental':True}})
            self.assertEqual(r.status_code,409)

    def test_package_failure_preserves_retryable_plan(self):
        s=self.create();s=self.edit(s,'set_parameter','rarity',{'value':'Rare'});s=self.act(s,'preview')
        before=s['plan']
        with patch('backend.workflow_v11.generate_draft',side_effect=RuntimeError('simulated failure')):
            s=self.act(s,'generate',{'digest':s['digest'],'confirmed':True,'accept_experimental':True})
            for _ in range(100):
                task=self.client.get('/api/v11/tasks/'+s['task_id']).json()
                if task['status']=='failed':break
                time.sleep(.02)
        self.assertEqual(task['status'],'failed')
        self.assertEqual(self.client.get('/api/v11/tasks/'+s['task_id']+'/download').status_code,409)
        s=self.act(s,'preview');self.assertEqual(s['plan'],before);self.assertTrue(s['ready'])

    def test_manual_resolution_only_closes_after_valid_edit(self):
        s=self.create();s=self.edit(s,'set_parameter','armor_class',{'value':20})
        issue=s['issues'][0]['id']
        s=self.act(s,'edit',{'resolve':[issue],'operations':[dict(kind='set_parameter',target='armor_class',payload={'value':20},group_id='g')]})
        self.assertIn(issue,[x['id'] for x in s['issues']])
        s=self.act(s,'edit',{'resolve':[issue],'quote':'改为稀有度调整以解决此要求','operations':[dict(kind='set_parameter',target='rarity',payload={'value':'Rare'},group_id='g')]})
        self.assertNotIn(issue,[x['id'] for x in s['issues']])

    def test_create_catalog_filters_unqualified_bases_and_keeps_modes_separate(self):
        c=self.client.get('/api/v11/catalog?kind=equipment&mode=create_new&limit=100').json()
        audit=self.resources['body_template_audit']['templates']
        self.assertTrue(c['items'])
        self.assertTrue(all(audit[x['id'].removeprefix('equipment:')]['qualified'] for x in c['items']))
        bad='equipment:00353281-1abb-4de6-893b-d6bf7f748da8'
        self.assertFalse(audit[bad.removeprefix('equipment:')]['qualified'])
        r=self.client.post('/api/v11/sessions',json={'mode':'create_new','base_equipment':bad})
        self.assertEqual(r.status_code,422)
        r=self.client.post('/api/v11/sessions',json={'mode':'modify_existing','base_equipment':bad})
        self.assertEqual(r.status_code,201)
        r=self.client.post('/api/v11/sessions',json={'mode':'create_new','base_equipment':self.fixtures['create_weapon']['base_equipment'],'inheritance':'retain_base','acquisition':'dammon_act1'})
        self.assertEqual(r.status_code,201);self.assertEqual(r.json()['plan']['acquisition'],'dammon_act1')
        self.assertNotIn('acquisition:unknown_or_unverified',r.json()['validation'])

    def test_legacy_unqualified_draft_can_switch_without_losing_free_name(self):
        s=self.create('create_new');runtime=self.app.state.craft.get(s['session_id'])
        old=runtime.draft.plan;old.base_equipment='equipment:00353281-1abb-4de6-893b-d6bf7f748da8'
        runtime.draft.replace(old,source='manual',expected_revision=runtime.draft.revision)
        self.app.state.craft.save(s['session_id'],runtime)
        s=self.client.get('/api/v11/sessions/'+s['session_id']).json()
        s=self.act(s,'edit',{'texts':[dict(target={'owner':'equipment','field':'name'},mode='exact',text='保留这个新名称',style=None)]})
        quote='切换基础装备并保留修改'
        s=self.act(s,'edit',{'quote':quote,'operations':[dict(kind='change_context',target='equipment',payload={'mode':'create_new','base_equipment':self.fixtures['create_weapon']['base_equipment'],'carry_policy':'revalidate','evidence_quote':quote},group_id='g')]})
        self.assertFalse(s['last_result']['failed'])
        s=self.edit(s,'set_inheritance_intent','equipment',{'strategy':'retain_base'})
        self.assertFalse(s['issues']);self.assertFalse(s['texts'])
        self.assertEqual(s['plan']['display']['name'],'保留这个新名称')

    def test_two_modes_real_package_download_and_feedback(self):
        for mode in ('modify_existing','create_new'):
            with self.subTest(mode=mode):
                s=self.create(mode);s=self.edit(s,'set_parameter','rarity',{'value':'Rare'})
                if mode=='create_new':
                    s=self.edit(s,'select_reference','acquisition',{'reference_id':'dammon_act1'})
                    s=self.act(s,'edit',{'texts':[dict(target={'owner':'equipment','field':'name'},mode='exact',text='接口验收装备',style=None)]})
                    s=self.act(s,'review')
                self.assertTrue(s['ready'],s)
                s=self.act(s,'preview')
                s=self.act(s,'generate',{'digest':s['digest'],'confirmed':True,'accept_experimental':True})
                ident=s['task_id']
                for _ in range(300):
                    task=self.client.get('/api/v11/tasks/'+ident).json()
                    if task['status'] not in ('queued','generating'):break
                    time.sleep(.1)
                self.assertEqual(task['status'],'succeeded',task)
                response=self.client.get('/api/v11/tasks/'+ident+'/download');self.assertEqual(response.status_code,200)
                import io,zipfile
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    self.assertIn('修改清单.json',z.namelist());self.assertIn('使用说明.txt',z.namelist())
                    self.assertIn('基础装备',z.read('使用说明.txt').decode())
                r=self.client.post('/api/v11/tasks/'+ident+'/feedback',json={'request_id':str(uuid.uuid4()),'outcome':'success','stage':'game_effect','game_version':'test','detail':'模拟反馈'})
                self.assertEqual(r.json()['game_validation'],'not_performed')
                if mode=='create_new':self.assertIn('达蒙',task['instructions'])

if __name__=='__main__':unittest.main()
