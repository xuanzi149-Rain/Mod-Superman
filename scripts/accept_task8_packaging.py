"""All B fixture families through task8 receipt/confirmation and real packaging."""
import datetime
import argparse
import json
import uuid
from backend.crafting_v11 import Plan
from backend.task8 import Task8Session
from scripts.crafting_compiler_v11 import load_resources,generate_draft
from scripts.equipment_catalog import load_catalog
from scripts.generate_mod import ROOT


def run(ids=None):
    r=load_resources();c=load_catalog();fixtures=json.loads((ROOT/'data/v1.1/phase-b-cases.json').read_text(encoding='utf-8'))
    out=ROOT/'build/v1.1/task8'/('independent-pack-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));out.mkdir(parents=True)
    rows=[]
    for key,value in fixtures.items():
        if ids and key not in ids:continue
        row={'case':key,'actor':'automated_fixture','model':'mock_review_not_real_model'}
        try:
            s=Task8Session(Plan.model_validate(value),c,r,inheritance='retain_base')
            if s.texts:
                ctx=s.review_context();review={'schema_version':'review-v1',**ctx['request'],'plan_digest':ctx['plan_digest'],
                    'items':[dict(text_id=t['id'],source_text_digest=t['source_text_digest'],source_status='consistent',findings=[],proposed_text=None,proposal_status='not_requested',proposal_findings=[]) for t in ctx['texts']]}
                s.apply_review(review,ctx)
            preview=s.preview()
            if preview['issues']:raise ValueError(preview['issues'])
            s.confirm(expected_revision=preview['revision'],expected_digest=preview['digest'])
            pak=generate_draft(s.draft,str(uuid.uuid4()),out,catalog=c,resources=r)
            result=json.loads((pak.parent/'result.json').read_text(encoding='utf-8'))
            row.update(status='passed',pak=str(pak.relative_to(ROOT)),pak_sha256=result['pak_sha256'],
                       stages={k:result[k] for k in ['source_generation','conversion','pak_creation','package_check','game_validation']})
        except Exception as err:row.update(status='failed',error=str(err))
        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        (out/'summary.json').write_text(json.dumps({'cases':rows,'game_validation':'not_performed'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(out,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--ids',nargs='*');run(parser.parse_args().ids)
