"""Frozen novel variants; never added to prompt examples. Retain every raw output."""
import datetime
import json
import time
from backend.task8_protocol import Task8Model, validate_output, VERSION
from backend.text_review_v11 import fingerprint
from scripts.generate_mod import ROOT


def run():
    path=ROOT/'docs/v1.1/task8/P4-新增验收变体.json'
    suite=json.loads(path.read_text(encoding='utf-8'))
    folder=ROOT/'build/v1.1/task8'/('p4-novel-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    folder.mkdir(parents=True);model=Task8Model();rows=[]
    for e in suite['cases']:
        row={'case':e,'prompt_version':VERSION,'model':model.model};start=time.monotonic()
        try:
            o,usage=model.run(e['task'],e['input']);row.update(output=o,usage=usage)
            validate_output(e['task'],o,e['input']);row['contract']='passed'
            expected=e['expectation'];checks={}
            if e['task']=='parse':
                checks['no_operations']=not o['operations']
                if expected.get('information_missing'):
                    checks['missing']=any(i['kind']=='information_missing' and i['question'] is None for i in o['issues'])
                if expected.get('text_owner'):
                    checks['target_and_text']=len(o['text_requests'])==1 and o['text_requests'][0]['target']['owner']==expected['text_owner'] and o['text_requests'][0]['text']==expected['exact_text']
                    checks['no_question']=not o['issues']
            else:
                checks={k:o['items'][0][k]==v for k,v in expected.items()}
            row.update(checks=checks,status='passed_mechanical_checks' if all(checks.values()) else 'needs_review')
        except Exception as err:row.update(status='failed',error=str(err))
        row.update(elapsed_ms=round((time.monotonic()-start)*1000),diagnostics=model.diagnostics)
        (folder/(e['id']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append({'case_id':e['id'],'status':row['status']});print(json.dumps(rows[-1]),flush=True)
    (folder/'summary.json').write_text(json.dumps({'cases':rows,'suite_fingerprint':fingerprint(path.read_text(encoding='utf-8')),'scope':'Four synthetic variants, not broad generalization evidence','prompt_version':VERSION},indent=2),encoding='utf-8')
    print(folder,flush=True)


if __name__=='__main__':run()
