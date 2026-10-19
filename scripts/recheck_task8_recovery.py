"""Recheck the first authorized case after repair, within the same six-call budget."""
import copy
import json
import time
from backend.task8 import Task8Session
from backend.task8_protocol import Task8Model, VERSION
from backend.model_client import settings, connection
from backend.crafting_v11 import Plan
from scripts.crafting_compiler_v11 import load_resources
from scripts.equipment_catalog import load_catalog
from scripts.generate_mod import ROOT

path=ROOT/'docs/v1.1/task8/v9-live-results.json'
evidence=json.loads(path.read_text(encoding='utf-8'))
manifest=json.loads((ROOT/'docs/v1.1/task8/v9-smoke-cases.json').read_text(encoding='utf-8-sig'))
selected=connection(settings())
assert selected['base_url']==manifest['endpoint'] and selected['model']==manifest['model']
assert not evidence.get('retests'), 'Do not repeat this completed batch'
row={'prompt':VERSION,'input':manifest['cases'][0],'calls':[]}
evidence['retests']=[row]
def save(): path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
class BoundedModel(Task8Model):
    def parse(self,request):
        if evidence['calls_started']>=6 or len(row['calls'])>=2: raise RuntimeError('Authorized budget exhausted')
        evidence['calls_started']+=1
        call={'number':evidence['calls_started'],'repair':request.get('repair')}
        row['calls'].append(call);save();start=time.monotonic()
        try:
            output,usage=super().parse(request);call.update(output=output,usage=usage);return output,usage
        except Exception as exc:
            call['error']=getattr(exc,'code',type(exc).__name__);raise
        finally:
            call['elapsed_seconds']=round(time.monotonic()-start,3);save()
session=Task8Session(Plan.model_validate(copy.deepcopy(evidence['results'][0]['before'])),load_catalog(),load_resources(),inheritance='retain_base')
session.model=BoundedModel();row['context']=session.context(row['input'],'v10_live_recheck')
try:
    row['result']=session.submit(row['input'],'v10_live_recheck')
    row['after']=session.draft.plan.model_dump(mode='json');row['issues']=list(session.issues.values())
except Exception as exc: row['error']=str(exc)
save()
print(json.dumps({'calls_total':evidence['calls_started'],'error':row.get('error'),'issues':row.get('issues')},ensure_ascii=False))
