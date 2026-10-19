"""Live-context independent acceptance, not prompt-example replay or website testing."""
import argparse
import copy
import datetime
import json
import time
from pathlib import Path
from backend.crafting_v11 import Plan
from backend.task8 import Task8Session, effective_values
from backend.task8_protocol import VERSION, messages
from backend.text_review_v11 import fingerprint
from scripts.crafting_compiler_v11 import load_resources, render_plan, check_files
from scripts.equipment_catalog import load_catalog
from scripts.generate_mod import ROOT


def definitions(fixtures):
    rows=[]
    def add(id,fixture,text,expect,**extra):rows.append(dict(id=id,fixture=fixture,text=text,expect=expect,**extra))
    for mode in ('modify_existing','create_new'):
        prefix='M' if mode=='modify_existing' else 'C'
        add(prefix+'01','create_weapon','伤害设为3d4，双手伤害3d6，伤害类型寒冷，附魔等级3，重量2.375千克，稀有度极珍稀，配置价值742。',
            {'parameters':{'damage':'3d4','versatile_damage':'3d6','damage_type':'Cold','enchantment':3,'weight_kg':2.375,'rarity':'VeryRare','value':742}},mode=mode)
        add(prefix+'02','create_body_armor','护甲等级设为19，敏捷加值上限2。',{'parameters':{'armor_class':19,'dexterity_rule':'capped_2'}},mode=mode)
        add(prefix+'03','create_weapon','给武器增加轻型特性，其余特性保留。',{'property':'Light'},mode=mode)
        add(prefix+'04','create_weapon','装备期间魅力提高3点。',{'effect':{'kind':'constant','ability':'Charisma','amount':3}},mode=mode)
        add(prefix+'05','create_weapon','装备期间奥秘技能检定加2，魅力豁免加1，并获得寒冷抗性。',{'effects':[{'kind':'bonus','bonus':'skill','selector':'Arcana','amount':2},{'kind':'bonus','bonus':'saving_throw','selector':'Charisma','amount':1},{'kind':'bonus','bonus':'resistance','selector':'Cold','amount':1}]},mode=mode)
        add(prefix+'06','create_weapon','每次命中后给自己恢复2d6生命，没有额外条件。',{'effect':{'kind':'trigger','event':'on_hit','condition':'always','target':'self','action':'heal','dice':'2d6'}},mode=mode)
        add(prefix+'07','create_body_armor','每次自己受到伤害后，无额外条件，给自己施加持续3回合的独立状态：护甲等级加2，不加属性，重复触发刷新持续时间。复用大步奔行的状态表现。',{'status_pair':3},mode=mode)
        add(prefix+'08','create_weapon','添加治愈真言独立技能，治疗3d4，距离21米，改用动作，长休恢复，取消法术位成本，其他资源成本保留。',{'effect':{'kind':'grant_spell','base_spell':'Target_HealingWord','healing':'3d4','range_m':21,'action_cost':'action','cooldown':'long_rest','remove_spell_slot':True}},mode=mode)
        add(prefix+'09','passive_copy','移除装备原有的平衡被动，换成它的独立副本，效果保持不变。',{'effect':{'kind':'passive_copy','base_passive':'ARM_Balance_1_Passive'},'removed':'ARM_Balance_1_Passive'},mode=mode)
    add('L01','create_weapon','重量先改为1.6千克。',{'parameters':{'weight_kg':1.6}},followup='再减少四分之一，按当前方案算。',followup_expect={'parameters':{'weight_kg':1.2}})
    add('L02','create_weapon','我想让它变得厉害一些。',{'blocked':True})
    add('L03','create_weapon','价值改为615，同时每杀一个敌人永久增加1点力量。',{'parameters':{'value':615},'blocked':True})
    add('L04','create_weapon','只把装备名称改为“晚潮”，不改变效果。',{'text_only':True,'text':'晚潮'})
    add('L05','create_weapon','恢复原装备的重量，保留其他修改。',{'parameters':{'weight_kg':None}},initial_parameters={'weight_kg':3,'value':500})
    add('L06','create_weapon','删除当前魅力加成词条，其他词条不变。',{'no_effect_id':'charisma'},initial_effects=[{'kind':'constant','id':'charisma','ability':'Charisma','amount':3},{'kind':'bonus','id':'speed','bonus':'movement','amount':2}])
    return rows


def check(s,result,expected):
    p=s.draft.plan.model_dump(mode='json');fail=[]
    if result['failed']:fail.append({'application_failed':result['failed']})
    for key,v in expected.get('parameters',{}).items():
        actual=p['parameters'][key] if v is None else effective_values(s.draft.plan,s.resources)[key]['current']
        if actual!=v:fail.append({'parameter':key,'actual':actual,'expected':v})
    for e in expected.get('effects',[])+([expected['effect']] if 'effect' in expected else []):
        if not any(all(x.get(k)==v for k,v in e.items()) for x in p['effects']):fail.append({'missing_effect':e})
    if 'property' in expected and expected['property'] not in (p['parameters']['weapon_properties'] or []):fail.append('missing_property')
    if 'removed' in expected and expected['removed'] not in p['removed_original_passives']:fail.append('original_passive_not_removed')
    if 'no_effect_id' in expected and any(e['id']==expected['no_effect_id'] for e in p['effects']):fail.append('effect_not_deleted')
    if expected.get('blocked') and not (s.issues or s.texts):fail.append('unresolved_requirement_lost')
    if expected.get('text_only'):
        if result['before']['parameters']!=result['after']['parameters'] or result['before']['effects']!=result['after']['effects']:fail.append('text_changed_mechanics')
        if not any(t['text']==expected['text'] for t in s.texts.values()):fail.append('missing_text_request')
    if 'status_pair' in expected:
        states=[e for e in p['effects'] if e['kind']=='independent_status'];triggers=[e for e in p['effects'] if e['kind']=='trigger']
        if not(len(states)==len(triggers)==1 and states[0]['duration_turns']==triggers[0]['duration_turns']==expected['status_pair'] and triggers[0]['status_draft_id']==states[0]['id'] and states[0]['stacking']=='replace' and states[0]['amount']==0 and any(b['bonus']=='armor_class' and b['amount']==2 for b in states[0]['bonuses'])):fail.append('incorrect_status_pair')
    return fail


def run(ids=None,prepare_only=False,suite_path=None):
    resources=load_resources();catalog=load_catalog();fixtures=json.loads((ROOT/'data/v1.1/phase-b-cases.json').read_text(encoding='utf-8'))
    target=ROOT/'docs/v1.1/task8/independent-acceptance'
    target.mkdir(parents=True,exist_ok=True);suite=Path(suite_path) if suite_path else target/'frozen-cases.json'
    if not suite.exists():suite.write_text(json.dumps(definitions(fixtures),ensure_ascii=False,indent=2),encoding='utf-8')
    cases=json.loads(suite.read_text(encoding='utf-8'));folder=ROOT/'build/v1.1/task8'/('independent-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));folder.mkdir(parents=True)
    results=[]
    for e in cases:
        if ids and e['id'] not in ids:continue
        p=copy.deepcopy(fixtures[e['fixture']]);p.update(parameters=e.get('initial_parameters',{}),effects=e.get('initial_effects',[]),display={},removed_original_passives=[])
        p['mode']=e.get('mode','modify_existing')
        if p['mode']=='modify_existing':p.update(acquisition=None,appearance_equipment=None)
        s=Task8Session(Plan.model_validate(p),catalog,resources,inheritance='retain_base');row={'case':e,'model':s.model.model,'version':VERSION,'initial_plan':p};start=time.monotonic()
        if prepare_only:
            c=s.context(e['text'],e['id']);payload=messages('parse',c)
            (folder/(e['id']+'.json')).write_text(json.dumps({'case':e,'messages':payload},ensure_ascii=False,indent=2),encoding='utf-8')
            results.append({'id':e['id'],'status':'prepared_no_network','chars':sum(len(m['content']) for m in payload)})
            continue
        try:
            result=s.submit(e['text'],e['id']);fail=check(s,result,e['expect']);row['first_result']=result
            if e.get('followup'):
                result=s.submit(e['followup'],e['id']+'_followup');fail+=check(s,result,e['followup_expect']);row['followup_result']=result
            row.update(failures=fail,status='passed' if not fail else 'failed')
            # Compile the accepted mechanics separately, without pretending missing user naming is resolved.
            if not s.issues and not e['expect'].get('text_only') and (s.draft.plan.mode!='create_new' or s.draft.plan.acquisition):
                preview=s.draft.plan;preview.unresolved=[];preview.display.name='自动化编译检查占位名' if preview.mode=='create_new' else None
                for effect in preview.effects:effect.display.description=None
                f,m=render_plan(preview,'00000000-0000-0000-0000-000000000088',catalog=catalog,resources=resources);check_files(f,m,resources)
                row['mechanical_compile']='passed_fixture_name_not_user_confirmation'
        except Exception as err:row.update(status='failed',error=str(err))
        row.update(log=s.log,elapsed_ms=round((time.monotonic()-start)*1000),final_plan=s.draft.plan.model_dump(mode='json'))
        (folder/(e['id']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8');results.append({'id':e['id'],'status':row['status']});print(json.dumps(results[-1]),flush=True)
    report={'cases':results,'suite_fingerprint':fingerprint(suite.read_text(encoding='utf-8')),'version':VERSION,'model':s.model.model,'scope':'Synthetic independent live-context acceptance; no website or game validation',
            'assets':{str(p.relative_to(ROOT)):fingerprint(p.read_text(encoding='utf-8')) for p in [ROOT/'backend/task8.py',ROOT/'backend/task8_protocol.py',ROOT/f'prompts/task8-parse-{VERSION.removeprefix("task8-")}.md',ROOT/f'prompts/task8-review-{VERSION.removeprefix("task8-")}.md']}}
    (folder/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(folder,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--ids',nargs='*');parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--suite');args=parser.parse_args();run(args.ids,args.prepare_only,args.suite)
