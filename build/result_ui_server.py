from pathlib import Path
import uvicorn
from backend.app import create_app
from backend.service import EquipmentService
from tests.test_workflow_v11 import FixedModel

class ResultModel(FixedModel):
    def run(self,task,c):
        if task=='review':return super().run(task,c)
        o,u=super().run(task,c)
        o['operations'][0].update(target='weight_kg',payload={'value':0,'unit':'kg'})
        o['intent_summary']='名字改为 Fool，重量改为 0'
        o['text_requests']=[dict(id='t1',requirement_ids=['r1'],target={'owner':'equipment','field':'name'},mode='exact',text='Fool',style=None)]
        o['requirements'][0].update(meaning=o['intent_summary'],text_request_ids=['t1'])
        return o,u

app=create_app(EquipmentService(root=Path('build/result-ui-test')),craft_model=ResultModel())
uvicorn.run(app,host='127.0.0.1',port=8768)
