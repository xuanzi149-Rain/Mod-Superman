"""Task8 development baseline. Preserve raw outputs; P3 judgments remain human-owned."""
import argparse
import copy
import datetime
import json
import time
from pathlib import Path
from backend.task8_protocol import Task8Model, examples, validate_output, VERSION
from backend.text_review_v11 import fingerprint
from scripts.generate_mod import ROOT


def projection(task, value):
    if task=='review':
        return [{'source_status':i['source_status'],'proposal_status':i['proposal_status']} for i in value['items']]
    return {'operations':[{k:o[k] for k in ('kind','target','payload')} for o in value['operations']],
            'issues':[i['kind'] for i in value['issues']],
            'texts':[{k:t[k] for k in ('target','mode','text')} for t in value['text_requests']]}


def run(real=False, limit=None):
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    folder=ROOT/'build/v1.1/task8'/('baseline-'+stamp);folder.mkdir(parents=True)
    model=Task8Model();rows=[]
    cases=examples()['parse_examples']+examples()['review_examples']
    if limit:cases=cases[:limit]
    for e in cases:
        case=copy.deepcopy(e);task=case['task'];context=case['input'];expected=case['expected_output']
        # Development replay, not a hidden holdout; label explicitly rather than claim generalization.
        row={'case_id':case['id'],'task':task,'source':'synthetic_development_replay',
             'prompt_version':VERSION,'context':context,'expected_output':expected,
             'mode':'real_model' if real else 'fixture_contract_check','p3_user_judgment':None}
        started=time.monotonic()
        try:
            output,usage=model.run(task,context) if real else (expected,None)
            row.update(output=output,usage=usage)
            validate_output(task,output,context)
            row['contract']='passed'
            row['projection_equal']=projection(task,output)==projection(task,expected)
            row['status']='matched_reference' if row['projection_equal'] else 'difference_needs_user_review'
        except Exception as error:
            row.update(status='failed',contract='failed',error_code=getattr(error,'code',type(error).__name__),error=str(error)[:3000])
        row.update(elapsed_ms=round((time.monotonic()-started)*1000),model=model.model,
                   diagnostics=model.diagnostics if real else None)
        (folder/(case['id']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append({k:row.get(k) for k in ('case_id','task','status','contract','projection_equal','elapsed_ms','error_code')})
        print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
    report={'run_id':folder.name,'mode':'real_model' if real else 'fixture_contract_check','model':model.model,
            'cases':rows,'count':len(rows),'p3_status':'decisions_recorded' if VERSION!='task8-v1' else 'awaiting_user_analysis',
            'note':'Development seed replay; examples may occur in prompt. Not holdout, user research, or game evidence.',
            'assets':{str(p.relative_to(ROOT)):fingerprint(p.read_text(encoding='utf-8')) for p in
                      [ROOT/f'prompts/task8-parse-{VERSION.removeprefix("task8-")}.md',ROOT/f'prompts/task8-review-{VERSION.removeprefix("task8-")}.md',ROOT/'data/v1.1/task8/parse-output.schema.json',ROOT/'data/v1.1/task8/review-output.schema.json',ROOT/'data/v1.1/task8/prompt-examples.json',ROOT/'backend/task8_protocol.py']}}
    (folder/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(folder),flush=True)
    return folder


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--real',action='store_true');parser.add_argument('--limit',type=int)
    args=parser.parse_args();run(args.real,args.limit)
