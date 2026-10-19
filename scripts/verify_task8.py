"""Programmatic task8 -> reviewed text -> B packaging acceptance, no HTTP/UI."""
import copy
import json
import uuid
from pathlib import Path
from backend.crafting_v11 import Plan, digest
from backend.task8 import Task8Session
from backend.task8_protocol import examples
from scripts.crafting_compiler_v11 import load_resources, generate_draft
from scripts.equipment_catalog import load_catalog
from scripts.generate_mod import ROOT


def verify():
    resources=load_resources();catalog=load_catalog()
    all_cases=json.loads((ROOT/'data/v1.1/phase-b-cases.json').read_text(encoding='utf-8'))
    reports=[]
    for key in ('modify_existing','create_weapon','create_body_armor'):
        p=Plan.model_validate(all_cases[key]);p.display.description=None
        payload=p.model_dump();payload['effects']=[{'kind':'constant','id':'dex_bonus','ability':'Dexterity','amount':2}]
        p=Plan.model_validate(payload)
        s=Task8Session(p,catalog,resources,inheritance='retain_base')
        context=s.context('说明改成‘装备期间，敏捷提高 2 点。’，效果参数不用动，只改文字。','verify_'+key)
        source=next(e for e in examples()['parse_examples'] if e['id']=='E09')
        output=copy.deepcopy(source['expected_output']);output.update(context['request'])
        output['requirements'][0]['quote']=context['latest_message']['text']
        output['text_requests'][0]['text']='装备期间，敏捷提高 2 点。'
        applied=s.apply(output,context)
        if applied['failed']:raise ValueError(applied['failed'])
        rc=s.review_context()
        reviewed={'schema_version':'review-v1',**rc['request'],'plan_digest':rc['plan_digest'],'items':[
            {'text_id':t['id'],'source_text_digest':t['source_text_digest'],'source_status':'consistent',
             'findings':[],'proposed_text':None,'proposal_status':'not_requested','proposal_findings':[]} for t in rc['texts']]}
        s.apply_review(reviewed,rc)
        preview=s.preview()
        if preview['issues']:raise ValueError(preview['issues'])
        s.confirm(expected_revision=preview['revision'],expected_digest=preview['digest'])
        pak_path=generate_draft(s.draft,str(uuid.uuid4()),ROOT/'build/v1.1/task8/acceptance',catalog=catalog,resources=resources)
        directory=pak_path.parent
        manifest=json.loads((directory/'result.json').read_text(encoding='utf-8'))
        reports.append({'case':key,'actor':'automated_fixture_not_user','model':'fixture_not_real_model',
            'directory':str(directory.relative_to(ROOT)),'revision':preview['revision'],'plan_digest':preview['digest'],
            'stages':{k:manifest[k] for k in ('source_generation','conversion','pak_creation','package_check','game_validation')},
            'pak_sha256':manifest['pak_sha256']})
        print(json.dumps(reports[-1],ensure_ascii=False),flush=True)
    result={'status':'passed','cases':reports,'game_validation':'not_performed','scope':'task8_python_to_B_no_HTTP_no_UI'}
    target=ROOT/'docs/v1.1/task8/task8-packaging-acceptance.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':verify()
