"""Full B acceptance: run regression, compile every target family, convert and check PAKs."""
import hashlib,json,os,re,subprocess,sys,uuid
from pathlib import Path
from backend.crafting_v11 import Plan,Draft,digest
from scripts.crafting_compiler_v11 import load_resources,generate_draft,ROOT
from scripts.equipment_catalog import load_catalog
from tests.test_compiler_v11 import example
from tests.test_phase_b_completion_v11 import new_plan,ARMOR,SHIELD,RING,AMULET,FIRST_BLOOD

def cases():
    weapon=example('create_new')
    weapon.parameters.enchantment=2;weapon.parameters.damage_type='Fire';weapon.parameters.versatile_damage='2d8'
    weapon.parameters.rarity='Rare';weapon.parameters.weapon_properties=['Versatile','Melee','Dippable','Finesse']
    armor=new_plan(ARMOR,parameters={'armor_class':18,'dexterity_rule':'full','value':300,'rarity':'Rare'},effects=[{'kind':'trigger','id':'heal','event':'on_damaged','condition':'always','target':'self','action':'heal','dice':'1d4','duration_turns':1}])
    status=new_plan(ARMOR,effects=[{'kind':'independent_status','id':'s','base_status':'BLESS','display':{'name':'独立防护状态'},'duration_turns':2,'stacking':'additive','ability':'Strength','amount':1,'bonuses':[{'kind':'bonus','id':'ac','bonus':'armor_class','amount':2}]},{'kind':'trigger','id':'t','event':'on_heal','condition':'always','target':'self','status_draft_id':'s','duration_turns':2}])
    return {
      'modify_existing':example(), 'create_weapon':weapon, 'create_body_armor':armor,
      'create_shield':new_plan(SHIELD,parameters={'armor_class':3}),
      'create_ring_with_reviewed_behavior':new_plan(RING),
      'armor_appearance_swap':new_plan(ARMOR,appearance_equipment='equipment:02ae5d88-8044-43df-8363-02a2900776db',icon='Item_ARM_Breastplate_2'),
      'special_gale_template':new_plan(FIRST_BLOOD,template_behavior='preserve_reviewed'),
      'independent_status':status,
      'passive_copy':Plan(mode='modify_existing',base_equipment='equipment:461f1cbe-6d0d-40ee-8bf6-8a68e0570d6f',user_goal='独立被动',removed_original_passives=['ARM_Balance_1_Passive'],effects=[{'kind':'passive_copy','id':'balance','base_passive':'ARM_Balance_1_Passive','display':{'name':'独立平衡'}}]),
      'status_spell_upcasts':new_plan(AMULET,effects=[{'kind':'grant_spell','id':'bless','base_spell':'Target_Bless','status_duration_turns':3,'spell_slot':{'level':2,'amount':1},'cooldown':'long_rest'}]),
      'delayed_heal':new_plan(AMULET,effects=[{'kind':'grant_spell','id':'radiance','base_spell':'Shout_HealingRadiance','healing':'2d4','area_radius_m':6.0}]),
      'damage_spell':new_plan(AMULET,effects=[{'kind':'grant_spell','id':'missile','base_spell':'Projectile_MagicMissile','damage':'2d4','range_m':24.0,'action_cost':'bonus_action','remove_spell_slot':True,'cooldown':'once_per_turn'}]),
      'container_spell':new_plan(AMULET,effects=[{'kind':'grant_spell','id':'orb','base_spell':'Projectile_ChromaticOrb','range_m':24.0}]),
    }

COVERAGE={
 'display_and_base_parameters':['modify_existing','create_weapon'],
 'weapon_damage_enchantment_properties':['create_weapon'],
 'armor_class_dexterity_and_shields':['create_body_armor','create_shield'],
 'constant_bonuses':['modify_existing'],
 'trigger_damage_healing_status':['modify_existing','create_body_armor','independent_status'],
 'independent_status_duration_stacking':['independent_status'],
 'spell_effect_range_cost_cooldown':['status_spell_upcasts','delayed_heal','damage_spell'],
 'compatible_visuals_icons_body_maps':['armor_appearance_swap','create_body_armor'],
 'new_equipment_acquisition':['create_weapon','create_body_armor','create_shield','create_ring_with_reviewed_behavior'],
 'native_dependencies_passives_upcasts_containers':['passive_copy','status_spell_upcasts','delayed_heal','container_spell'],
 'special_template_behavior':['special_gale_template'],
}

def main():
    output=ROOT/'docs/v1.1/phase-b-acceptance.json'
    report={'date':'2026-10-17','status':'running','game_validation':'not_performed','coverage':COVERAGE,'cases':[]}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        env=dict(os.environ);tmp=ROOT/'build/v1.1/test-tmp';tmp.mkdir(parents=True,exist_ok=True)
        env['TEMP']=env['TMP']=str(tmp)
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,env=env,capture_output=True,timeout=180)
        log=ROOT/'build/v1.1/phase-b-tests.log';log.write_bytes(result.stdout+result.stderr)
        text=log.read_text(encoding='utf-8',errors='replace');match=re.search(r'Ran (\d+) tests in ([\d.]+)s',text)
        tests={'result':'passed' if result.returncode==0 else 'failed','tests':int(match[1]) if match else None,'elapsed_seconds':float(match[2]) if match else None,'log':'build/v1.1/phase-b-tests.log','log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'game_validation':'not_performed'}
        (ROOT/'docs/v1.1/phase-b-tests.json').write_text(json.dumps(tests,indent=2),encoding='utf-8')
        report['regression']=tests
        if result.returncode:raise RuntimeError('Full regression failed; see phase-b-tests.log')
        print('Regression passed:',tests['tests'],flush=True)
        resources,catalog=load_resources(),load_catalog();plans=cases()
        (ROOT/'data/v1.1/phase-b-cases.json').write_text(json.dumps({k:p.model_dump(mode='json') for k,p in plans.items()},ensure_ascii=False,indent=2),encoding='utf-8')
        for name,plan in plans.items():
            draft=Draft(plan);issues=draft.review(catalog,resources)
            if issues:raise ValueError(name+':'+str(issues))
            draft.confirm(expected_revision=draft.revision,expected_digest=digest(plan))
            module_id=str(uuid.uuid5(uuid.UUID('e9190ef1-0290-49b5-995a-503f35c97b3f'),name))
            pak=generate_draft(draft,module_id,ROOT/'build/v1.1/phase-b',catalog=catalog,resources=resources)
            manifest=json.loads((pak.parent/'result.json').read_text(encoding='utf-8'))
            report['cases'].append({'name':name,'mode':plan.mode,'plan_digest':digest(plan),'pak':str(pak.relative_to(ROOT)),
                'checks':{k:manifest[k] for k in ('source_generation','conversion','pak_creation','package_check','game_validation','pak_sha256')},
                'dependency_copies':sum(len(m) for m in manifest['native_dependency_copies'].values())})
            print('PAK verified:',name,flush=True)
        required={n for names in COVERAGE.values() for n in names}
        assert required==set(plans)
        audit=resources['body_template_audit']
        report.update(status='passed',tasks={'4':'passed','5':'passed','6':'passed','7':'passed'},
            resource_evidence={'native_body_profiles':len(audit['races']),'qualified_templates':sum(v['qualified'] for v in audit['templates'].values()),'body_asset_inputs':len(audit['inputs_sha256']),'base_catalog_inputs':len(resources['inputs_sha256'])},
            scope='All agreed target capability categories and task 4-7 criteria; native data/PAK acceptance only, not all original records or arbitrary combinations.',
            deferred=['C: AI semantic review, HTTP/persistence/UI/download integration','D: model evaluation and evidence synthesis','gameplay, external users and public deployment'])
    except Exception as e:
        report.update(status='failed',error=str(e));raise
    finally:
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Phase B acceptance passed.',flush=True)

if __name__=='__main__':main()
