"""Local C regression, fixed review response plus actual B packaging; no live LLM."""
import hashlib
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from collections import Counter
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.service import EquipmentService
from scripts.crafting_compiler_v11 import load_resources
from scripts.equipment_catalog import load_catalog
from scripts.generate_mod import ROOT
from tests.test_workflow_v11 import FixedModel

KEY='025e162a-45ec-4f4c-89da-04d8e8dfe606'

def main():
    resources=load_resources();catalog=load_catalog();audit=resources['body_template_audit']
    before=json.loads((ROOT/'build/v1.1/weapon-index-before.json').read_text(encoding='utf-8'))
    models={x.split('\t')[0].casefold() for x in (ROOT/'build/v1.1/all-models.log').read_text(encoding='utf-8-sig').splitlines()}
    groups={};new=[];lost=[];counts=Counter();reasons=Counter()
    for ident,item in catalog['items'].items():
        key=ident.removeprefix('equipment:');t=resources['templates'][key];a=audit['templates'][key]
        visual=audit['visuals'].get(t['effective'].get('VisualTemplate',{}).get('value'),{})
        group=groups.setdefault(item['category'],Counter())
        flags={'total':True,'model_record_found':bool(visual),'model_file_listed':bool(visual and visual['SourceFile'].casefold() in models),'qualified_before':before[ident]['qualified'],'qualified_after':a['qualified']}
        for name,value in flags.items():counts[name]+=bool(value);group[name]+=bool(value)
        if a['qualified'] and not before[ident]['qualified']:new.append({'id':ident,'name':item['display_name']})
        if before[ident]['qualified'] and not a['qualified']:lost.append(ident)
        if not a['qualified']:reasons.update(a['issues'])
    assert not lost,lost
    service=EquipmentService(root=ROOT/'build/v1.1/weapon-index-acceptance')
    app=create_app(service,craft_model=FixedModel())
    try:
        with TestClient(app) as client:
            rows=client.get('/api/v11/catalog',params={'kind':'equipment','mode':'create_new','search':'地脉迷城'}).json()['items']
            assert any(x['id']=='equipment:'+KEY for x in rows)
            response=client.post('/api/v11/sessions',json={'mode':'create_new','base_equipment':'equipment:'+KEY,'inheritance':'retain_base','acquisition':'dammon_act1'})
            assert response.status_code==201,response.text
            s=response.json()
            def action(name,data):
                nonlocal s
                response=client.post('/api/v11/sessions/'+s['session_id']+'/'+name,json={'revision':s['revision'],'request_id':str(uuid.uuid4()),'data':data})
                assert response.status_code==200,response.text
                s=response.json()
            action('edit',{'texts':[{'target':{'owner':'equipment','field':'name'},'mode':'exact','text':'地脉迷城之王的匕首·独立副本','style':None}]})
            assert not s['last_result']['failed'],s
            action('review',{});action('preview',{})
            assert s['ready'],s['validation']
            assert all(v is None for v in s['plan']['parameters'].values())
            assert s['plan']['effects']==[] and s['plan']['removed_original_passives']==[]
            action('generate',{'digest':s['digest'],'confirmed':True,'accept_experimental':True})
            for _ in range(600):
                task=client.get('/api/v11/tasks/'+s['task_id']).json()
                if task['status'] not in ('queued','generating'):break
                time.sleep(.1)
            assert task['status']=='succeeded',task
            response=client.get('/api/v11/tasks/'+s['task_id']+'/download')
            assert response.status_code==200
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                files=archive.namelist();manifest=json.loads(archive.read('修改清单.json'))
                assert manifest['plan']['display']['name']=='地脉迷城之王的匕首·独立副本'
                assert any(x.endswith('.pak') for x in files)
            target={'id':'equipment:'+KEY,'visual':audit['visuals'][resources['templates'][KEY]['effective']['VisualTemplate']['value']],
                    'audit':audit['templates'][KEY],'task_id':s['task_id'],'plan':manifest['plan'],'checks':task['checks'],
                    'zip':str((service.root/'v11-downloads'/(s['task_id']+'.zip')).relative_to(ROOT)),
                    'zip_sha256':hashlib.sha256(response.content).hexdigest(),'zip_entries':files,'version':task['version']}
    finally:app.state.jobs.close()
    report={'date':'2026-10-17','denominator':'website catalog records, not distinct names or all game equipment',
            'counts':dict(counts),'by_category':groups,'newly_qualified':new,'regressed':lost,'remaining_issue_counts_nonexclusive':dict(reasons),
            'target':target,'model_evidence':'fixed response, no live call','game_validation':'not_performed','phase_D':'not_started'}
    (ROOT/'docs/v1.1/weapon-index-fix-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'counts':counts,'target_checks':target['checks'],'target_task':target['task_id']},ensure_ascii=False))

if __name__=='__main__':main()
