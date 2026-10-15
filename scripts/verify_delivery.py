"""Real packager + HTTP delivery acceptance. Fixture AI is explicitly labelled."""
import argparse
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.service import EquipmentService, write_json
from scripts.generate_equipment import FIRST_BLOOD
from scripts.generate_mod import ROOT


class Fixture:
    model = 'fixture-not-real-api'
    def parse(self, context):
        return {'result':'suggestion','operations':[
            {'field':'damage','operation':'set','value':'2d6','basis':'current','unit':None},
            {'field':'name','operation':'set','value':'赤霄<&短剑','basis':'current','unit':None},
            {'field':'weight_kg','operation':'multiply','value':.5,'basis':'current','unit':None}],
            'questions':[],'unsupported':[],'explanation':'固定验收响应，非真实模型。'}, None


def verify(real=False, root=None):
    service=EquipmentService(root=Path(root) if root else ROOT/'build/backend/delivery-verification'/str(uuid.uuid4()))
    app=create_app(service,None if real else Fixture())
    with TestClient(app) as client:
        def post(url,body):
            r=client.post(url,json=body)
            if r.status_code>=400:
                diagnostic=None
                if '/sessions/' in url:
                    identifier=url.split('/sessions/',1)[1].split('/')[0]
                    history=app.state.ai.get(identifier).get('history',[])
                    if history:diagnostic=history[-1].get('model_diagnostics')
                failure=dict(model_mode='real_api' if real else 'fixture',result='failed',
                    actor='automated_acceptance',http_status=r.status_code,error=r.json().get('detail'),
                    model_diagnostics=diagnostic,game_validation='not_performed')
                write_json(service.root/'verification.json',failure)
                print(json.dumps(failure,ensure_ascii=True,indent=2),flush=True)
                raise RuntimeError('Acceptance failed; see '+str(service.root/'verification.json'))
            return r.json()
        state=post('/api/ai/sessions',{'object':FIRST_BLOOD})
        session='/api/ai/sessions/'+state['session_id']
        state=post(session+'/messages',{'version':0,'request_id':str(uuid.uuid4()),
            'text':'把基础伤害改为2d6，中文名称改为“赤霄<&短剑”，重量改为原重量的一半。'})
        assert state['draft']=={'damage':'2d6','name':'赤霄<&短剑','weight_kg':.45},state['draft']
        state=post(session+'/preview',{'version':state['version'],'request_id':str(uuid.uuid4())})
        plan=state['preview'];url='/api/plans/'+plan['plan_id']
        assert client.post(url+'/tasks',json={'confirmed':False}).status_code==409
        post(url+'/tasks',{'confirmed':True,'accept_experimental':True})
        for _ in range(300):
            plan=client.get(url).json()
            if plan['status'] not in ('queued','generating'):break
            time.sleep(.1)
        assert plan['status']=='succeeded',plan
        archive=client.get(url+'/download');assert archive.status_code==200
        with zipfile.ZipFile(io.BytesIO(archive.content)) as package:
            assert package.testzip() is None and len(package.namelist())==3
        instruction=client.get(url+'/instructions').json()['text']
        assert plan['plan_id'] in instruction
        feedback=post(url+'/feedback',dict(request_id=str(uuid.uuid4()),outcome='problem',stage='game_effect',
            game_version='automated-test',detail='自动验收反馈；没有进行游戏测试，不计入玩家结果。'))
        assert feedback['evidence']=='user_report'
        with service.store.connect() as db:
            events=db.execute('SELECT count(*) FROM events').fetchone()[0]
            feedbacks=db.execute('SELECT count(*) FROM feedback').fetchone()[0]
        report=dict(model_mode='real_api' if real else 'fixture',provider=getattr(app.state.ai.model,'provider','fixture'),
            model=app.state.ai.model.model,packager=str(service.packager),
            session_id=state['session_id'],plan_id=plan['plan_id'],stages=plan['stages'],
            zip_check=plan['zip_check'],download_bytes=len(archive.content),events=events,feedbacks=feedbacks,
            game_validation='not_performed',actor='automated_acceptance',result='passed')
        write_json(service.root/'verification.json',report)
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--real',action='store_true');parser.add_argument('--root')
    args=parser.parse_args();verify(args.real,args.root)
