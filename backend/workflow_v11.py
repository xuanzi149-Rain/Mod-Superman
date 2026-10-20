"""Versioned HTTP workflow over task8; SQLite state, bounded B delivery, no v1 migration."""
import copy
import hashlib
import json
import threading
import time
import uuid
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from backend.crafting_v11 import Plan, Draft, digest
from backend.task8 import Task8Session, effective_values
from backend.task8_protocol import VERSION, schema
from backend.text_review_v11 import fingerprint, valid_receipt, COMPILER_VERSION
from backend.storage import now
from backend.player_language import player_issue
from backend.workflow_errors import explain_failure
from backend.service import ServiceError
from scripts.crafting_compiler_v11 import load_resources, generate_draft, validate_plan
from scripts.generate_mod import ROOT

SESSION_FIELDS = ('inheritance','issues','texts','history','requests','snapshots','goal','requirements','latest_review','normalizations')


class CraftService:
    def __init__(self, service, jobs, model=None):
        self.service, self.store, self.jobs, self.model = service, service.store, jobs, model
        self.catalog, self.resources = service.catalog(), load_resources()
        self.sessions = {}; self.cache_lock = threading.RLock()
        self.names = {}
        for n in ET.parse(ROOT/'.tools/equipment-chinese.xml').getroot():
            self.names[(n.get('contentuid'),n.get('version'))] = ''.join(n.itertext())
        self.version = {'prompt':VERSION,'compiler':COMPILER_VERSION,'resources':fingerprint(self.resources),
                        'catalog':fingerprint(self.catalog),'schema':'1.1-draft-4'}
        with self.store.connect() as db:
            rows=db.execute("SELECT id,payload FROM records WHERE kind='v11_tasks'").fetchall()
        for ident,payload in rows:
            task=json.loads(payload)
            if task['status'] in ('queued','generating'):
                task.update(status='interrupted',failure_stage='service_restart')
                self.store.snapshot('v11_tasks',ident,task)

    def name(self, ref):
        raw=self.resources['records'].get(ref,{}).get('effective',{}).get('DisplayName','')
        parts=raw.split(';')
        return self.names.get((parts[0],parts[1] if len(parts)>1 else '1'),ref)

    def candidates(self, kind, search='', offset=0, limit=30, *, mode=None):
        if kind=='equipment':
            values=[{'id':k,'name':v['display_name'],'category':v['category']} for k,v in self.catalog['items'].items()]
            if mode=='create_new':
                audit=self.resources.get('body_template_audit',{}).get('templates',{})
                values=[v for v in values if audit.get(v['id'].removeprefix('equipment:'),{}).get('qualified')]
        elif kind=='acquisition':
            values=[{'id':a['id'],'name':a['name'],'limitations':a['limitations']} for a in self.resources['acquisition_entries']]
        elif kind=='icon':
            values=[{'id':k,'name':k} for k,v in self.resources['icon_asset_validation'].items() if v.get('asset_exists')]
        elif kind in ('SpellData','StatusData','PassiveData'):
            values=[{'id':k,'name':self.name(k)} for k,v in self.resources['records'].items() if v['type']==kind]
        else:raise ServiceError('unknown_catalog','目录类型不存在。',404)
        values=[v for v in values if search.casefold() in (v['name']+' '+v['id']).casefold()]
        return {'items':values[offset:offset+limit],'total':len(values),'version':self.version,'candidate_only':True}

    def history(self, visitor):
        with self.store.connect() as db:
            rows=db.execute("SELECT r.kind,r.id,r.payload,r.updated_at FROM records r JOIN owners o ON r.kind=o.kind AND r.id=o.id WHERE o.token_hash=? AND r.kind IN ('v11_sessions','v11_tasks') AND NOT (r.kind='v11_sessions' AND EXISTS (SELECT 1 FROM records d WHERE d.kind='v11_deleted_drafts' AND d.id=r.id)) ORDER BY r.updated_at DESC LIMIT 50",(self.store.token_hash(visitor),)).fetchall()
        return {'items':[{'kind':kind,'id':ident,'updated_at':stamp,'mode':json.loads(payload)['plan']['mode'],
                         'name':json.loads(payload)['plan'].get('display',{}).get('name') or self.catalog['items'].get(json.loads(payload)['plan']['base_equipment'],{}).get('display_name','历史装备'),
                         'status':json.loads(payload).get('status','draft'),'session_id':json.loads(payload).get('session_id',ident)} for kind,ident,payload,stamp in rows]}

    def delete_draft(self, ident, visitor):
        if not self.store.allowed('v11_sessions', ident, visitor):
            raise ServiceError('not_found', '草稿不存在或不属于当前浏览器。', 404)
        session = self.get(ident)
        if not session.lock.acquire(blocking=False):
            raise ServiceError('session_busy', '草稿正在处理，请稍后删除。', 409)
        try:
            with self.store.connect() as db:
                tasks = db.execute("SELECT payload FROM records WHERE kind='v11_tasks'").fetchall()
            if any((t := json.loads(row[0])).get('session_id') == ident and t.get('status') in ('queued', 'generating') for row in tasks):
                raise ServiceError('generation_busy', '方案正在制作中，请完成后再删除草稿。', 409)
            # Keep the session snapshot for existing delivery records; remove only the draft entry.
            self.store.snapshot('v11_deleted_drafts', ident, {'deleted_at': now()})
            return {'status': 'deleted', 'session_id': ident}
        finally:
            session.lock.release()

    def create(self, body, visitor):
        p=Plan(mode=body['mode'],base_equipment=body['base_equipment'],user_goal=body.get('goal') or '装备定制')
        if p.base_equipment not in self.catalog['items']:raise ServiceError('unknown_base','请从目录选择基础装备。',422)
        if p.mode=='create_new':
            audit=self.resources.get('body_template_audit',{}).get('templates',{}).get(p.base_equipment.removeprefix('equipment:'),{})
            if not audit.get('qualified'):
                raise ServiceError('base_not_ready','这件装备暂时不能作为新装备来源，请选择列表中已检查的基础装备。',422)
            acquisition=body.get('acquisition')
            if acquisition is not None:
                if acquisition not in ('camp_chest','dammon_act1'):
                    raise ServiceError('invalid_acquisition','请选择列表中的获取地点。',422)
                p.acquisition='camp_chest'
        elif body.get('acquisition') is not None:
            raise ServiceError('unexpected_acquisition','修改已有装备保留原获取方式。',422)
        ident=str(uuid.uuid4());s=Task8Session(p,self.catalog,self.resources,model=self.model,inheritance=body.get('inheritance'))
        s.http_requests={};s.last_result=None;s.last_error=None;s.task_id=None;s.recovery=None
        self.sessions[ident]=s;self.store.claim('v11_sessions',ident,visitor);self.save(ident,s)
        return self.view(ident,s)

    def save(self, ident, s):
        value={k:copy.deepcopy(getattr(s,k)) for k in SESSION_FIELDS}
        value.update(plan=s.draft.plan.model_dump(mode='json'),revision=s.draft.revision,version=self.version,
                     http_requests=s.http_requests,last_result=s.last_result,last_error=s.last_error,task_id=s.task_id,
                     updated_at=now(),record_version=1,recovery=s.recovery)
        # Receipts are deliberately not serialized: restart requires a fresh review.
        self.store.snapshot('v11_sessions',ident,value)

    def get(self, ident):
        with self.cache_lock:
            if ident in self.sessions:return self.sessions[ident]
            saved=self.store.get('v11_sessions',ident)
            if not saved:raise ServiceError('not_found','制作会话不存在。',404)
            if saved.get('record_version')!=1 or saved['plan'].get('schema_version')!='1.1-draft-4':
                raise ServiceError('incompatible_draft','旧草稿不兼容，请保留历史记录并新建方案。',409)
            s=Task8Session(Plan.model_validate(saved['plan']),self.catalog,self.resources,model=self.model,inheritance=saved['inheritance'])
            for k in SESSION_FIELDS:setattr(s,k,copy.deepcopy(saved[k]))
            s.issues={key:player_issue(value) for key,value in s.issues.items()}
            s.draft=Draft(Plan.model_validate(saved['plan']));s.draft.revision=saved['revision']+1
            # Failed inputs are no longer persistent tasks. Keep actual plan constraints.
            s.issues={}
            s.inheritance='retain_base'
            s.draft.plan.unresolved=[v['detail'] for v in s.issues.values()]
            s.history=[h for h in s.history if not h.get('feedback',{}).get('unresolved') and not h.get('feedback',{}).get('failed')]
            s.requirements=[]
            for snapshot in s.snapshots.values():
                snapshot['issues']={}
                snapshot['inheritance']='retain_base'
                snapshot['plan']['unresolved']=[v['detail'] for v in snapshot['issues'].values()]
            s.http_requests=saved.get('http_requests',{});s.last_result=saved.get('last_result');s.last_error=None;s.task_id=saved.get('task_id')
            s.latest_review=None;s.recovery='服务已重启，草稿已恢复；请重新核对并确认。'
            s._queue_existing_texts()
            self.sessions[ident]=s;self.save(ident,s)
            return s

    def view(self, ident, s=None):
        s=s or self.get(ident);p=s.draft.plan
        key=(p.appearance_equipment or p.base_equipment).removeprefix('equipment:')
        native=self.resources['records'][self.resources['templates'][p.base_equipment.removeprefix('equipment:')]['stats']]['effective']
        refs=list(filter(None,native.get('PassivesOnEquip','').split(';')))
        audit=self.resources.get('body_template_audit',{}).get('templates',{}).get(key,{})
        reference_names={r:self.name(r) for r in refs}
        for e in p.effects:
            reference_names[e.id]=e.display.name or {'independent_status':'独立状态','grant_spell':'主动技能','trigger':'条件触发'}.get(e.kind,'独立效果')
            for field in ('base_spell','base_status','base_passive','status_ref'):
                ref=getattr(e,field,None)
                if ref:reference_names[ref]=self.name(ref)
        errors=validate_plan(p,self.catalog,self.resources,text_receipt=s.draft.text_receipt)
        return {'session_id':ident,'revision':s.draft.revision,'digest':digest(p),'plan':p.model_dump(mode='json'),
                'has_parsed':any(h.get('parsed',True) for h in s.history) or bool(p.effects or p.removed_original_passives or s.texts)
                    or any(v is not None for v in p.parameters.model_dump().values())
                    or any(v is not None for v in p.display.model_dump().values()),
                'effective_values':effective_values(p,self.resources),'issues':[player_issue(i,names=reference_names) for i in s.issues.values()],
                'texts':list(s.texts.values()),'review':s.latest_review['output'] if s.latest_review else None,
                'validation':errors,'ready':not(errors or s.issues or s.texts),'version':self.version,
                'last_result':s.last_result,'last_error':({k:v for k,v in s.last_error.items() if k!='details'} if s.last_error else None),'task_id':s.task_id,'recovery':s.recovery,
                'base_name':self.catalog['items'][p.base_equipment]['display_name'],
                'original_passives':[{'id':r,'name':self.name(r),'removed':r in p.removed_original_passives} for r in refs],
                'template_audit':audit,'template_audit_id':'template_'+fingerprint(audit)[:16],
                'reference_names':reference_names,'inheritance':s.inheritance,
                'snapshots':[{'id':k,'revision':v['revision']} for k,v in s.snapshots.items()],
                'game_validation':'not_performed'}

    def manual(self,s,body):
        ops=copy.deepcopy(body.get('operations',[]));texts=copy.deepcopy(body.get('texts',[]))
        if not isinstance(ops,list) or not isinstance(texts,list) or len(ops)>60 or len(texts)>60:raise ValueError('invalid_edit')
        quote=body.get('quote','手动修改方案')
        message=quote+'\n'+'\n'.join(t.get('text') or '' for t in texts)
        c=s.context(message,str(uuid.uuid4()),expanded=True)
        for item in ops:
            if set(item)-{'kind','target','payload','group_id'}:raise ValueError('invalid_operation_fields')
            # Only server-catalogued references enter manual context, never invented resources.
            payload=item.get('payload',{});value=payload.get('effect',payload.get('changes',{}))
            if item.get('kind')=='set_parameter':payload.setdefault('unit','kg' if item.get('target')=='weight_kg' else None)
            refs=[payload.get('reference_id'),payload.get('base_equipment')]+[value.get(k) for k in ('base_spell','base_status','base_passive','status_ref')]
            for ref in refs:
                if ref and (ref in self.resources['records'] or ref in self.catalog['items'] or ref in self.resources['icon_asset_validation']):
                    c['capabilities']['candidates'].append({'id':ref})
        ops=[dict(x,id='op'+str(i),requirement_ids=['manual']) for i,x in enumerate(ops)]
        texts=[dict(x,id='text'+str(i),requirement_ids=['manual']) for i,x in enumerate(texts)]
        updates=[]
        for i,issue in enumerate(body.get('withdraw',[])):
            if issue not in s.issues:raise ValueError('unknown_issue')
            updates.append({'id':'withdraw'+str(i),'issue_id':issue,'proposed_action':'withdrawn','evidence_quote':quote,'operation_ids':[],'text_request_ids':[]})
        for i,issue in enumerate(body.get('resolve',[])):
            if issue not in s.issues or not (ops or texts):raise ValueError('unknown_or_empty_resolution')
            updates.append({'id':'resolve'+str(i),'issue_id':issue,'proposed_action':'answered','evidence_quote':quote,
                            'operation_ids':[x['id'] for x in ops],'text_request_ids':[x['id'] for x in texts]})
        # Use the task8 contract for manual actions, including dependency groups and stale bindings.
        requirement={'id':'manual','quote':quote,'meaning':quote,'operation_ids':[x['id'] for x in ops],
                     'text_request_ids':[x['id'] for x in texts],'issue_ids':[],
                     'issue_update_ids':[x['id'] for x in updates],'no_change':not(ops or texts or updates)}
        output={'schema_version':'parse-v1',**c['request'],'intent_summary':quote,'requirements':[requirement],
                'operations':ops,'text_requests':texts,'issues':[],'issue_updates':updates}
        return s.apply(output,c)

    def action(self,ident,action,body,visitor):
        s=self.get(ident)
        if not s.lock.acquire(blocking=False):raise ServiceError('session_busy','正在处理上一条请求，草稿已保留。',409)
        started=time.monotonic();old_logs=len(s.log)
        try:
            key=body['request_id'];mark=fingerprint({'action':action,'body':body})
            previous=s.http_requests.get(key)
            if previous:
                if previous['fingerprint']!=mark:raise ServiceError('request_conflict','同一请求编号不能提交不同内容。',409)
                return {**self.view(ident,s),'operation_result':previous['result']}
            if body['revision']!=s.draft.revision:raise ServiceError('stale_revision','草稿已更新，请刷新后重新操作。',409)
            if s.task_id:
                task=self.store.get('v11_tasks',s.task_id)
                if task and task['status'] in ('queued','generating'):raise ServiceError('generation_busy','制作中，请等待完成再修改。',409)
            data=body.get('data',{})
            if action=='message':
                text=data.get('text','')
                if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('invalid_message')
                previous={k:copy.deepcopy(getattr(s,k)) for k in SESSION_FIELDS}
                previous_draft=copy.deepcopy(s.draft)
                result=s.submit(text,key,answers=data.get('answers',[]))
                if result.get('unresolved') or result.get('failed'):
                    for failure in result.get('failed',[]):
                        s.log.append({'task':'validation_failure','error':failure.get('error'),'request_id':key})
                    feedback=[player_issue(i) for i in result.get('unresolved',[])]
                    if not feedback:
                        feedback=[{'detail':'本次修改未通过检查，暂时无法确定具体原因。'}]
                    for k,v in previous.items():setattr(s,k,v)
                    s.draft=previous_draft
                    # Transient response only: no failed input, pending issue, request
                    # cache, snapshot or revision is persisted by this submission.
                    return {**self.view(ident,s),'input_retained':True,'input_feedback':feedback}
                if result.get('before') == result.get('after'):
                    # Answers and no-ops must not save the submitted text or invalidate
                    # a previously confirmed draft. Return feedback only for this request.
                    reply=result.get('assistant_response','').strip()
                    for k,v in previous.items():setattr(s,k,v)
                    s.draft=previous_draft
                    response={**self.view(ident,s),'input_retained':True,'assistant_response':reply}
                    if not reply:
                        response['input_feedback']=[{'detail':'本次输入没有产生修改，模型也没有提供具体回答；暂时无法确定原因。'}]
                    return response
            elif action=='edit':result=self.manual(s,data)
            elif action=='review':result=s.review_text() if s.texts else s.preview()
            elif action=='adopt':result=s.adopt_review(replacements=data.get('replacements',[]))
            elif action=='standard':result={'validation':s.use_standard_text()}
            elif action=='preview':result=s.preview()
            elif action=='generate':result=self.submit(ident,s,data,visitor)
            else:raise ServiceError('unknown_action','操作不存在。',404)
            if action in ('message','edit','review','adopt','standard'):s.task_id=None
            s.last_result=result;s.last_error=None;s.recovery=None
            s.http_requests[key]={'fingerprint':mark,'result':result}
            self.save(ident,s)
            return {**self.view(ident,s),'operation_result':result,'assistant_response':result.get('assistant_response','')}
        except ServiceError as error:
            s.last_error={'stage':action,'code':error.code,'message':error.message};self.save(ident,s);raise
        except (ValueError,KeyError,TypeError,StopIteration) as error:
            s.last_error={'stage':action,'code':'invalid_operation','message':explain_failure(action,error),'details':str(error)[:1600]}
            self.save(ident,s)
            raise ServiceError('invalid_operation',s.last_error['message'],422) from None
        finally:
            try:
                for i,entry in enumerate(s.log[old_logs:],old_logs):
                    self.store.snapshot('v11_model_calls',ident+':'+str(uuid.uuid4()),{'session_id':ident,'request_id':body['request_id'],
                        'task':entry.get('task'),'usage':entry.get('usage'),'error':entry.get('error'),
                        'model':getattr(s.model,'model',None),'provider':getattr(s.model,'provider',None),
                        'version':self.version,'created_at':now()})
                self.store.event(str(uuid.uuid4()),ident,s.task_id,action,'failed' if s.last_error else 'completed',
                                 {'revision':s.draft.revision,'elapsed_ms':round((time.monotonic()-started)*1000),'version':self.version})
            finally:
                if action=='message':del s.log[old_logs:]
                s.lock.release()

    def submit(self,ident,s,data,visitor):
        if data.get('confirmed') is not True or data.get('accept_experimental') is not True:
            raise ServiceError('confirmation_required','请确认当前方案及尚未游戏实测的提示。',409)
        if data.get('digest')!=digest(s.draft.plan):raise ValueError('stale_digest')
        # Detect changed source files even when the long-lived process cached its catalog.
        fresh=load_resources()
        if fingerprint(fresh)!=self.version['resources'] or fingerprint(self.service.catalog())!=self.version['catalog']:
            raise ServiceError('stale_catalog','资源或目录已更新，请重启服务、恢复草稿并重新核对。',409)
        if not self.jobs.slots.acquire(blocking=False):raise ServiceError('generation_capacity','制作任务已满，请稍后重试。',429)
        try:
            s.confirm(expected_revision=s.draft.revision,expected_digest=data['digest'])
            task_id=str(uuid.uuid4());snapshot=s.draft.plan.model_dump(mode='json')
            task={'task_id':task_id,'session_id':ident,'status':'queued','plan':snapshot,'revision':s.draft.revision,
                  'digest':data['digest'],'version':self.version,'created_at':now(),'game_validation':'not_performed'}
            self.store.claim('v11_tasks',task_id,visitor);self.store.snapshot('v11_tasks',task_id,task)
            s.task_id=task_id
            self.jobs.executor.submit(self.run_task,task_id,s.draft)
            return {'task_id':task_id,'status':'queued'}
        except Exception:
            self.jobs.slots.release();raise

    def run_task(self,ident,draft):
        task=self.store.get('v11_tasks',ident)
        try:
            task['status']='generating';self.store.snapshot('v11_tasks',ident,task)
            pak=generate_draft(draft,ident,self.service.root/'v11-packages',catalog=self.catalog,resources=self.resources,packager=self.service.packager)
            report=json.loads((pak.parent/'result.json').read_text(encoding='utf-8'))
            instructions=(pak.parent/'使用说明.txt').read_text(encoding='utf-8')
            p=task['plan'];base=self.catalog['items'][p['base_equipment']]
            instructions+='\n基础装备：'+base['display_name']+'\n资源及依赖：详见修改清单.json；复用原生资源，不安装运行时脚本。\n反馈中报告生效不等于独立游戏验证。'
            archive=self.service.root/'v11-downloads'/(ident+'.zip');archive.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                z.write(pak,pak.name);z.writestr('使用说明.txt',instructions)
                z.writestr('修改清单.json',json.dumps({'plan':p,'base_name':base['display_name'],'version':task['version'],
                    'digest':task['digest'],'checks':{k:v for k,v in report.items() if k!='error'}},ensure_ascii=False,indent=2))
            task.update(status='succeeded',generated_at=now(),instructions=instructions,
                        checks={k:report[k] for k in ('source_generation','conversion','pak_creation','package_check','game_validation')},
                        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        except Exception as error:
            stages=['source_generation','conversion','pak_creation','package_check'];stage='validation'
            reports=list((self.service.root/'v11-packages'/ident).rglob('result.json'))
            if reports:
                report=json.loads(reports[-1].read_text(encoding='utf-8'));stage=next((k for k in stages if report.get(k)!='passed'),'delivery')
            task.update(status='failed',failure_stage=stage,error_type=type(error).__name__)
        finally:
            try:self.store.snapshot('v11_tasks',ident,task)
            finally:self.jobs.slots.release()

    def task(self,ident):
        result=self.store.get('v11_tasks',ident)
        if not result:raise ServiceError('not_found','制作任务不存在。',404)
        return result

    def download(self,ident):
        task=self.task(ident);path=self.service.root/'v11-downloads'/(str(uuid.UUID(ident))+'.zip')
        if task['status']!='succeeded' or not path.is_file():raise ServiceError('download_unavailable','文件尚未就绪或已清理，请重新预览并制作。',409)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=task['archive_sha256']:raise ServiceError('archive_changed','文件校验失败，请重新制作。',409)
        return path
