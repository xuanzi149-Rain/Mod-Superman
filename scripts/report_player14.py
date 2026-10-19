"""Read isolated UI-test evidence; never submits requests or invokes a model."""
import json,sqlite3
from pathlib import Path
from scripts.generate_mod import ROOT

def main():
    db=sqlite3.connect('file:'+str(ROOT/'build/v1.1/player14-data/records.sqlite3')+'?mode=ro',uri=True)
    cases=json.loads((ROOT/'docs/v1.1/player14-cases.json').read_text(encoding='utf-8'))
    sessions=[(i,json.loads(p)) for i,p in db.execute("SELECT id,payload FROM records WHERE kind='v11_sessions' ORDER BY updated_at")]
    rows=[]
    for case in cases:
        matches=[]
        for ident,s in sessions:
            inputs=[h['user'] for h in s.get('history',[])]
            if case['inputs'][0] in inputs:
                matches.append({'session':ident,'inputs':inputs,'revision':s['revision'],'plan':s['plan'],
                                'issues':s['issues'],'texts':s['texts'],'last_error':s.get('last_error'),
                                'last_result':s.get('last_result'),'task_id':s.get('task_id'),'version':s.get('version')})
        rows.append({'id':case['id'],'expect':case['expect'],'runs':matches})
    tasks=[json.loads(p) for p, in db.execute("SELECT payload FROM records WHERE kind='v11_tasks'")]
    events=[{'session':sid,'stage':stage,'result':result,**json.loads(details or '{}')}
            for sid,stage,result,details in db.execute('SELECT session_id,stage,result,details FROM events ORDER BY created_at')]
    model_calls=[json.loads(p) for p, in db.execute("SELECT payload FROM records WHERE kind='v11_model_calls' ORDER BY updated_at")]
    report={'source':'14 browser UI scenarios; isolated local website; configured real model','cases':rows,'tasks':tasks,
            'events':events,'model_calls':model_calls,'extra_debug_calls':1,'game_validation':'not_performed'}
    (ROOT/'docs/v1.1/player14/results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([{'id':r['id'],'runs':len(r['runs']),'error':r['runs'][-1]['last_error'] if r['runs'] else None} for r in rows],ensure_ascii=False))
if __name__=='__main__':main()
