"""Authorized three-case live smoke test, with a persisted six-call ceiling."""
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

OUT=ROOT/'docs/v1.1/task8/v9-live-results.json'
MANIFEST=ROOT/'docs/v1.1/task8/v9-smoke-cases.json'

def main():
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8-sig'))
    selected=connection(settings())
    if selected['base_url'] != manifest['endpoint'] or selected['model'] != manifest['model']:
        raise RuntimeError('Configured endpoint/model differs from authorized batch')
    if OUT.exists():
        raise RuntimeError('Evidence already exists; do not accidentally repeat authorized calls')
    evidence={'prompt':VERSION,'synthetic':True,'call_limit':6,'calls_started':0,'results':[]}
    def save(): OUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    resources=load_resources(); catalog=load_catalog()
    base=json.loads((ROOT/'data/v1.1/phase-b-cases.json').read_text(encoding='utf-8'))['modify_existing']
    base.update(parameters={},effects=[],removed_original_passives=[],display={})
    for index,text in enumerate(manifest['cases']):
        row={'input':text,'calls':[]}; evidence['results'].append(row)
        class BoundedModel(Task8Model):
            def parse(self,request):
                if evidence['calls_started']>=6 or len(row['calls'])>=2:
                    raise RuntimeError('Authorized batch call budget exhausted')
                evidence['calls_started']+=1
                call={'number':evidence['calls_started'],'repair':request.get('repair')}
                row['calls'].append(call); save()
                start=time.monotonic()
                try:
                    output,usage=super().parse(request)
                    call.update(output=output,usage=usage)
                    return output,usage
                except Exception as exc:
                    call['error']=getattr(exc,'code',type(exc).__name__)
                    raise
                finally:
                    call['elapsed_seconds']=round(time.monotonic()-start,3);save()
        session=Task8Session(Plan.model_validate(copy.deepcopy(base)),catalog,resources,inheritance='retain_base')
        session.model=BoundedModel()
        row['context']=session.context(text,'v9_live_'+str(index))
        row['before']=session.draft.plan.model_dump(mode='json')
        try:
            row['result']=session.submit(text,'v9_live_'+str(index))
            row['after']=session.draft.plan.model_dump(mode='json')
            row['issues']=list(session.issues.values())
        except Exception as exc:
            row['error']=str(exc)
        save()
        print(json.dumps({'case':index+1,'input':text,'calls':len(row['calls']),'error':row.get('error'),'issues':row.get('issues'),'after_parameters':row.get('after',{}).get('parameters')},ensure_ascii=False),flush=True)
    print('calls_started='+str(evidence['calls_started']),flush=True)

if __name__=='__main__': main()
