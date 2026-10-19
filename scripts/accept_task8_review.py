"""Real text review on the same authorized independent-case plans, never game validation."""
import argparse
import datetime
import json
from pathlib import Path
from backend.crafting_v11 import Plan
from backend.task8 import Task8Session
from scripts.crafting_compiler_v11 import load_resources,render_plan,check_files
from scripts.equipment_catalog import load_catalog
from scripts.generate_mod import ROOT


def run(source, ids):
    source=Path(source);r=load_resources();c=load_catalog()
    out=ROOT/'build/v1.1/task8'/('independent-review-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));out.mkdir(parents=True);rows=[]
    for key in ids:
        record=json.loads((source/(key+'.json')).read_text(encoding='utf-8'))
        s=Task8Session(Plan.model_validate(record['final_plan']),c,r,inheritance='retain_base');row={'case_id':key,'source':str(source.relative_to(ROOT)),'model':s.model.model}
        # Synthetic acceptance actor explicitly requests prose for this case's effects.
        for effect in s.draft.plan.effects:
            slot=effect.id+':description';s.texts[slot]={'id':slot,'target':{'owner':effect.id,'field':'description'},'mode':'rewrite','text':None,
                'style':'用中文准确说明该词条的触发、条件、对象、数值、持续时间、资源成本和限制；只依据提供的最终事实，不增加效果。'}
        try:
            result=s.review_text();row['result']=result
            if result['pending']:raise ValueError('review_unresolved')
            preview=s.preview()
            if preview['issues']:raise ValueError(preview['issues'])
            files,manifest=render_plan(s.draft.plan,'00000000-0000-0000-0000-000000000089',catalog=c,resources=r,text_receipt=s.draft.text_receipt)
            check_files(files,manifest,r)
            row.update(status='protocol_adoption_compile_passed_semantic_read_required',final_plan=s.draft.plan.model_dump(mode='json'))
        except Exception as e:row.update(status='failed',error=str(e))
        row['log']=s.log;(out/(key+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8');rows.append({'id':key,'status':row['status']});print(json.dumps(rows[-1]),flush=True)
    (out/'summary.json').write_text(json.dumps({'cases':rows,'scope':'same authorized synthetic cases, real review and compilation, no packaging or game run'},indent=2),encoding='utf-8');print(out,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('--ids',nargs='+',required=True);args=parser.parse_args();run(args.source,args.ids)
