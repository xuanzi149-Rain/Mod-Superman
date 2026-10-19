"""Phase B completion regression: native files and adversarial dependency/asset cases."""
import copy
import unittest
import xml.etree.ElementTree as ET
from backend.crafting_v11 import Plan
from scripts.crafting_compiler_v11 import load_resources,render_plan,validate_plan,check_files
from scripts.equipment_catalog import load_catalog,parse_stats
from scripts.native_dependencies_v11 import closure,replace_amount
from tests.test_compiler_v11 import MODULE,FIRST_BLOOD,OLD_PASSIVE,LONGSWORD

ARMOR='equipment:4814825e-23ee-41ed-9784-d9963434150d'
SHIELD='equipment:004ab562-5cd4-4f1f-8aa5-497e7e2c5f4f'
RING='equipment:5492c9bb-31a9-4f30-bfd4-935ff97c8eaf'
AMULET='equipment:179c4e2f-a568-40be-b9c6-25c2541aeb12'

def new_plan(base,**kwargs):
    if base == RING and 'template_behavior' not in kwargs:
        kwargs['template_behavior']='preserve_reviewed'
    return Plan(mode='create_new',base_equipment=base,user_goal='B整体验收固定案例',display={'name':'独立装备'},acquisition='dammon_act1',**kwargs)

class CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=load_resources();cls.c=load_catalog()
    def compile(self,p):
        f,m=render_plan(p,MODULE,catalog=self.c,resources=self.r);check_files(f,m,self.r)
        records={v.name:v for path,data in f.items() if path.parent.name=='Data' for v in parse_stats(data.decode(),str(path))}
        return f,m,records

    def test_armor_all_native_bodies_resolve(self):
        a=self.r['body_template_audit']['templates'][ARMOR[10:]]
        self.assertTrue(a['qualified']);self.assertEqual(len(a['body_mapping']),25)
        self.assertEqual(a['body_mapping']['7dd0aa66-5177-4f65-b7d7-187c02531b0b']['resolved_race'],'7d73f501-f65e-46af-a13b-2cacf3985d05')
        for body in a['body_mapping'].values():
            self.assertTrue(body['visuals']);self.assertFalse(body['missing_models'])

    def test_armor_creation_preserves_complete_template(self):
        f,m,r=self.compile(new_plan(ARMOR,parameters={'armor_class':18,'dexterity_rule':'capped_2'}))
        xml=ET.fromstring(next(b for p,b in f.items() if p.name=='_merged.lsx'))
        self.assertEqual(xml.find('.//attribute[@id="ParentTemplateId"]').get('value'),ARMOR[10:])
        self.assertNotIn('ARM_Breastplate_Body',r)
        self.assertEqual(r[m['equipment']].fields['ArmorClass'],'18')

    def test_shield_ring_amulet_need_no_body_mesh(self):
        for base in (SHIELD,RING,AMULET):
            with self.subTest(base=base):
                _,m,_=self.compile(new_plan(base));self.assertTrue(m['template_audit']['qualified'])

    def test_same_slot_armor_appearance(self):
        f,m,r=self.compile(new_plan(ARMOR,appearance_equipment='equipment:02ae5d88-8044-43df-8363-02a2900776db'))
        xml=ET.fromstring(next(b for p,b in f.items() if p.name=='_merged.lsx'))
        self.assertEqual(xml.find('.//attribute[@id="ParentTemplateId"]').get('value'),'02ae5d88-8044-43df-8363-02a2900776db')
        self.assertEqual(r[m['equipment']].parent,'ARM_Breastplate_Body')

    def test_unknown_or_incompatible_template_rejected(self):
        p=new_plan(ARMOR,appearance_equipment=LONGSWORD)
        self.assertTrue(validate_plan(p,self.c,self.r))
        bad=copy.deepcopy(self.r['body_template_audit']['templates'][ARMOR[10:]])
        bad['qualified']=False;bad['issues']=['body_model_missing:test']
        audit=dict(self.r['body_template_audit']);audit['templates']=dict(audit['templates']);audit['templates'][ARMOR[10:]]=bad
        resources=dict(self.r);resources['body_template_audit']=audit
        self.assertTrue(any('body_model_missing' in s for s in validate_plan(new_plan(ARMOR),self.c,resources)))

    def test_special_behavior_explicit_and_auditable(self):
        self.assertTrue(validate_plan(new_plan(FIRST_BLOOD),self.c,self.r))
        _,m,_=self.compile(new_plan(FIRST_BLOOD,template_behavior='preserve_reviewed'))
        self.assertTrue(any(x.get('kind')=='gale_consumption' for x in m['template_audit']['special_actions']))
        self.assertIn('7b96246c-54ba-43ea-b01d-4e0b20ad35f1',m['template_audit']['inherited_tags'])

    def test_armor_on_damaged_healing(self):
        p=new_plan(ARMOR,effects=[{'kind':'trigger','id':'heal','event':'on_damaged','condition':'always','target':'self','action':'heal','dice':'1d4','duration_turns':1}])
        _,m,r=self.compile(p);self.assertEqual(r[m['effect_ids']['heal']].fields['StatsFunctorContext'],'OnDamaged')

    def test_recursive_healing_rejected(self):
        p=new_plan(ARMOR,effects=[{'kind':'trigger','id':'heal','event':'on_heal','condition':'always','target':'self','action':'heal','dice':'1d4','duration_turns':1}])
        self.assertTrue(any('recursive' in s for s in validate_plan(p,self.c,self.r)))

    def test_generic_passive_copy(self):
        p=Plan(mode='modify_existing',base_equipment='equipment:461f1cbe-6d0d-40ee-8bf6-8a68e0570d6f',user_goal='独立被动',removed_original_passives=['ARM_Balance_1_Passive'],effects=[{'kind':'passive_copy','id':'balance','base_passive':'ARM_Balance_1_Passive'}])
        _,m,r=self.compile(p);self.assertNotIn('ARM_Balance_1_Passive',r)
        self.assertEqual(r[m['effect_ids']['balance']].fields['Boosts'],self.r['records']['ARM_Balance_1_Passive']['effective']['Boosts'])

    def test_status_spell_family_remaps_all_refs(self):
        p=new_plan(RING,effects=[{'kind':'grant_spell','id':'bless','base_spell':'Target_Bless','status_duration_turns':3}])
        _,m,r=self.compile(p);mapping=m['native_dependency_copies']['bless']
        self.assertEqual(len(mapping),13)
        self.assertEqual(r[mapping['Target_Bless']].fields['SpellProperties'],f"ApplyStatus({mapping['BLESS']}, 100, 3)")
        self.assertIn(', 100, 3)',r[mapping['Target_Bless_AI']].fields['SpellProperties'])
        self.assertEqual(mapping['Target_Bless_2'],mapping['Target_Bless']+'_2')
        self.assertEqual(r[mapping['BLESS']].fields['StackId'],mapping['BLESS'])
        self.assertFalse(set(mapping)&set(r))

    def test_delayed_heal_dependency_preserved_and_updated(self):
        p=new_plan(AMULET,effects=[{'kind':'grant_spell','id':'radiance','base_spell':'Shout_HealingRadiance','healing':'2d4','area_radius_m':6.0}])
        _,m,r=self.compile(p);mapping=m['native_dependency_copies']['radiance']
        self.assertEqual(len(mapping),3)
        self.assertIn(mapping['HEALING_RADIANCE'],r[mapping['Shout_HealingRadiance']].fields['SpellProperties'])
        self.assertIn(mapping['Shout_HealingRadiance_Heal'],r[mapping['HEALING_RADIANCE']].fields['OnRemoveFunctors'])
        linked=r[mapping['Shout_HealingRadiance_Heal']].fields
        self.assertEqual(linked['SpellProperties'],'RegainHitPoints(2d4);');self.assertEqual(linked['AreaRadius'],'6.0')
        self.assertEqual(linked['UseCosts'],'')

    def test_dependency_cycles_missing_and_unknown_functions(self):
        for records in ({'A':{'type':'StatusData','effective':{'OnApplyFunctors':'ApplyStatus(A,100,1)'}}},
                        {'A':{'type':'SpellData','effective':{'SpellProperties':'ApplyStatus(MISSING,100,1)'}}},
                        {'A':{'type':'SpellData','effective':{'SpellProperties':'UnknownFunction(1)'}}}):
            with self.assertRaises(ValueError):closure('A',records)

    def test_dependency_descriptions_match_final_values(self):
        p=new_plan(AMULET,effects=[{'kind':'grant_spell','id':'spell','base_spell':'Target_Bless','status_duration_turns':3}])
        files,m,r=self.compile(p)
        texts={n.get('contentuid'):n.text for path,raw in files.items() if path.suffix=='.xml' for n in ET.fromstring(raw).iter('content')}
        upcast=r[m['native_dependency_copies']['spell']['Target_Bless_2']].fields
        self.assertIn(upcast['UseCosts'],texts[upcast['Description'].split(';')[0]])
        self.assertEqual(upcast['DescriptionParams'],'')
        p=new_plan(AMULET,effects=[{'kind':'grant_spell','id':'heal','base_spell':'Shout_HealingRadiance','healing':'2d4'}])
        _,m,r=self.compile(p)
        status=r[m['native_dependency_copies']['heal']['HEALING_RADIANCE']].fields
        self.assertEqual(status['DescriptionParams'],'')

    def test_immunity_and_predicates_do_not_clone_their_targets(self):
        self.assertEqual(closure('Alert',self.r['records']),['Alert'])
        sample={'A':{'type':'PassiveData','effective':{'Conditions':"HasStatus('B')",'Boosts':'AC(1)'}},'B':{'type':'StatusData','effective':{}}}
        self.assertEqual(closure('A',sample),['A'])

    def test_container_family_includes_siblings_without_false_cycle(self):
        sample={'Target_A':{'type':'SpellData','effective':{'ContainerSpells':'Target_B;Target_C'}},
                'Target_B':{'type':'SpellData','effective':{'SpellContainerID':'Target_A'}},
                'Target_C':{'type':'SpellData','effective':{'SpellContainerID':'Target_A'}}}
        self.assertEqual(set(closure('Target_B',sample)),set(sample))

    def test_real_chromatic_orb_children_and_upcasts(self):
        p=new_plan(AMULET,effects=[{'kind':'grant_spell','id':'orb','base_spell':'Projectile_ChromaticOrb','range_m':24.0}])
        _,m,r=self.compile(p);mapping=m['native_dependency_copies']['orb']
        self.assertEqual(len(mapping),37)
        for element in ('Acid','Cold','Fire','Lightning','Poison','Thunder'):
            base='Projectile_ChromaticOrb_'+element
            self.assertEqual(r[mapping[base]].fields['TargetRadius'],'24.0')
            self.assertEqual(mapping[base+'_2'],mapping[base]+'_2')
            self.assertEqual(r[mapping[base+'_2']].fields['RootSpellID'],mapping[base])

    def test_missing_level_map_rejected(self):
        resources=dict(self.r);audit=dict(resources['body_template_audit']);audit['level_maps']={};resources['body_template_audit']=audit
        p=new_plan(AMULET,effects=[{'kind':'grant_spell','id':'spell','base_spell':'Projectile_FireBolt'}])
        self.assertTrue(any('unknown_level_map' in s for s in validate_plan(p,self.c,resources)))

    def test_native_cost_definition_required(self):
        resources=dict(self.r);audit=dict(resources['body_template_audit']);audit['action_resources']={};resources['body_template_audit']=audit
        p=new_plan(RING,effects=[{'kind':'grant_spell','id':'spell','base_spell':'Target_CureWounds'}])
        self.assertTrue(any('unknown_action_resource' in s for s in validate_plan(p,self.c,resources)))

    def test_nested_formula_replacement_keeps_other_effects(self):
        self.assertEqual(replace_amount('RegainHitPoints(ClassLevel(Paladin)+Cause.CharismaModifier);ApplyStatus(X,100,1)','RegainHitPoints','2d6'),'RegainHitPoints(2d6);ApplyStatus(X,100,1)')

    def test_independent_status_additive_and_protection(self):
        p=new_plan(ARMOR,effects=[{'kind':'independent_status','id':'s','base_status':'BLESS','display':{'name':'独立防护'},'duration_turns':2,'stacking':'additive','ability':'Strength','amount':1,'bonuses':[{'kind':'bonus','id':'ac','bonus':'armor_class','amount':2}]},{'kind':'trigger','id':'t','event':'on_damaged','condition':'always','target':'self','status_draft_id':'s','duration_turns':2}])
        _,m,r=self.compile(p);s=r[m['effect_ids']['s']].fields
        self.assertEqual(s['StackType'],'Additive');self.assertEqual(s['Boosts'],'Ability(Strength,1);AC(2)')

if __name__=='__main__':unittest.main()
