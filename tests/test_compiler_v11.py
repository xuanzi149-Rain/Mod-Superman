import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import xml.etree.ElementTree as ET
from backend.crafting_v11 import Plan, Draft, digest
from scripts.equipment_catalog import load_catalog, parse_stats
from scripts.crafting_compiler_v11 import load_resources, render_plan, validate_plan, check_files, generate_draft, FIRST_BLOOD, OLD_PASSIVE

MODULE = 'ba8908da-5806-4eed-a55e-d098142c21ba'
LONGSWORD = 'equipment:1865323f-b428-4791-a0a9-578841e57463'


def example(mode='modify_existing'):
    return Plan(mode=mode, base_equipment=FIRST_BLOOD if mode == 'modify_existing' else LONGSWORD,
                user_goal='程序验收案例，非玩家使用记录', display={'name':'测试装备', 'description':'测试背景'},
                acquisition='dammon_act1' if mode == 'create_new' else None,
                parameters={'damage':'2d6', 'weight_kg':1.25, 'value':300},
                effects=[{'kind':'constant','id':'ability','ability':'Strength','amount':2},
                         {'kind':'bonus','id':'initiative','bonus':'initiative','amount':2},
                         {'kind':'bonus','id':'movement','bonus':'movement','amount':3},
                         {'kind':'bonus','id':'skill','bonus':'skill','selector':'Stealth','amount':1},
                         {'kind':'bonus','id':'save','bonus':'saving_throw','selector':'Wisdom','amount':1},
                         {'kind':'bonus','id':'ac','bonus':'armor_class','amount':1},
                         {'kind':'bonus','id':'resistance','bonus':'resistance','selector':'Fire'},
                         {'kind':'independent_status','id':'status','base_status':'LONGSTRIDER','display':{'name':'力量状态'},'duration_turns':2,'stacking':'ignore','ability':'Strength','amount':1},
                         {'kind':'trigger','id':'apply','event':'on_hit','condition':'target_full_health','target':'self','status_draft_id':'status','duration_turns':2},
                         {'kind':'trigger','id':'damage','event':'on_hit','condition':'always','target':'target','action':'damage','dice':'1d4','damage_type':'Fire','duration_turns':1},
                         {'kind':'trigger','id':'heal','event':'on_hit','condition':'always','target':'self','action':'heal','dice':'1d4','duration_turns':1},
                         {'kind':'grant_spell','id':'spell','base_spell':'Target_HealingWord','healing':'2d4','range_m':24.0,'action_cost':'action','remove_spell_slot':True,'cooldown':'short_rest'}])


class CompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = load_resources()
        cls.c = load_catalog()

    def render(self, p):
        files, manifest = render_plan(p,MODULE,catalog=self.c,resources=self.r)
        check_files(files,manifest,self.r)
        records = {s.name:s for path,b in files.items() if path.parent.name=='Data' for s in parse_stats(b.decode(),str(path))}
        return files,manifest,records

    def test_all_effect_families(self):
        f,m,r=self.render(example())
        self.assertEqual(r[m['effect_ids']['ability']].fields['Boosts'],'Ability(Strength,2)')
        self.assertEqual(r[m['effect_ids']['movement']].fields['Boosts'],'ActionResource(Movement,3,0)')
        self.assertEqual(r[m['effect_ids']['status']].fields['StackType'],'Ignore')
        self.assertIn('RegainHitPoints(SELF,1d4)',r[m['effect_ids']['heal']].fields['StatsFunctors'])
        self.assertIn(OLD_PASSIVE,r[m['equipment']].fields['PassivesOnEquip'])

    def test_independent_spell_and_cost(self):
        f,m,r=self.render(example())
        spell=r[m['effect_ids']['spell']]
        self.assertIsNone(spell.parent)
        self.assertEqual(spell.fields['SpellType'],'Target')
        self.assertEqual(spell.fields['UseCosts'],'ActionPoint:1')
        self.assertEqual(spell.fields['Cooldown'],'OncePerShortRest')
        self.assertEqual(spell.fields['SpellProperties'],'RegainHitPoints(2d4)')
        self.assertNotIn('Target_HealingWord',r)

    def test_new_equipment_and_acquisition(self):
        f,m,r=self.render(example('create_new'))
        self.assertNotEqual(m['equipment'],'WPN_Longsword')
        self.assertNotIn('WPN_Longsword',r)
        self.assertFalse(any(p.name=='TreasureTable.txt' for p in f))
        t=next(v.decode() for p,v in f.items() if p.name=='OneTimeRewards.lsx')
        self.assertIn(m['root_template'],t)
        self.assertIn('OneTimeReward',t)

    def test_stable_identity(self):
        p=example('create_new'); a=self.render(p);b=self.render(p)
        self.assertEqual(a[:2],b[:2])
        _, other=render_plan(p,'741b405c-f3e0-4c4b-bc69-2fd15f14ff13',catalog=self.c,resources=self.r)
        self.assertNotEqual(a[1]['root_template'],other['root_template'])

    def test_existing_template_children_preserved(self):
        f,m,r=self.render(example())
        node=ET.fromstring(next(v for p,v in f.items() if p.name=='_merged.lsx'))
        self.assertIsNotNone(node.find('.//node[@id="OnUsePeaceActions"]'))
        self.assertEqual(len(node.findall('.//attribute[@id="DisplayName"]')),1)

    def test_honour_removal(self):
        p=example(); p.removed_original_passives=[OLD_PASSIVE]
        _,m,r=self.render(p)
        self.assertNotIn(OLD_PASSIVE,r[m['equipment']].fields['PassivesOnEquip'])
        self.assertEqual(r[m['equipment']].fields['DefaultBoosts'],'WeaponProperty(Magical)')

    def test_reject_unresolved_and_unknown_skill(self):
        p=example();p.unresolved=['未实现的目标']
        self.assertIn('unresolved_questions',validate_plan(p,self.c,self.r))
        p=example();p.effects[-1].base_spell='Unknown'
        self.assertTrue(validate_plan(p,self.c,self.r))

    def test_reject_wrong_type_and_unknown_bonus(self):
        p=example();p.parameters.armor_class=20
        self.assertTrue(validate_plan(p,self.c,self.r))
        p=example();p.effects[3].selector='arbitrary_function'
        self.assertTrue(validate_plan(p,self.c,self.r))

    def test_reject_hidden_story_actions(self):
        p=example('create_new');p.base_equipment=FIRST_BLOOD
        self.assertIn('base_equipment:special_behavior_requires_acknowledgement',validate_plan(p,self.c,self.r))

    def test_allow_text_without_semantic_review(self):
        p=example();p.effects[0].display.description='增加100点力量'
        self.assertFalse(validate_plan(p,self.c,self.r))

    def test_armor_dexterity(self):
        key=next(k for k,v in self.c['items'].items() if v['record']=='ARM_Breastplate_Body')
        p=Plan(mode='modify_existing',base_equipment=key,user_goal='护甲',parameters={'armor_class':17,'dexterity_rule':'full'})
        _,m,r=self.render(p)
        self.assertEqual(r[m['equipment']].fields['Armor Class Ability'],'Dexterity')
        self.assertEqual(r[m['equipment']].fields['Ability Modifier Cap'],'')

    def test_spell_damage_and_area(self):
        for payload, field, expected in [({'base_spell':'Projectile_FireBolt','damage':'2d6'},'SpellSuccess','DealDamage(2d6,Fire,Magical)'),({'base_spell':'Shout_HealingRadiance','healing':'2d4','area_radius_m':6.0},'AreaRadius','6.0')]:
            p=Plan(mode='modify_existing',base_equipment=FIRST_BLOOD,user_goal='技能',effects=[{'kind':'grant_spell','id':'spell',**payload}])
            _,m,r=self.render(p)
            self.assertEqual(r[m['effect_ids']['spell']].fields[field],expected)

    def test_confirmation_resource_change(self):
        p=example();d=Draft(p)
        self.assertEqual(d.review(self.c,self.r),[])
        d.confirm(expected_revision=1,expected_digest=digest(p))
        r=dict(self.r);r['ruleset']='changed'
        with self.assertRaises(ValueError):d.begin_generation(self.c,r)

    def test_unconfirmed_cannot_generate(self):
        with self.assertRaises(ValueError):Draft(example()).begin_generation(self.c,self.r)

    def test_checker_detects_dangling_reference(self):
        f,m,_=self.render(example())
        path=next(p for p in f if p.name=='Weapon.txt')
        f[path]=f[path].replace(OLD_PASSIVE.encode(),b'NONEXISTENT')
        with self.assertRaises(ValueError):check_files(f,m,self.r)

    def test_parameter_enchantment_and_properties(self):
        p=example('create_new');p.parameters.enchantment=2
        p.parameters.weapon_properties=['Versatile','Melee','Dippable','Finesse']
        _,m,r=self.render(p)
        self.assertEqual(r[m['equipment']].fields['DefaultBoosts'],'WeaponEnchantment(2)')
        self.assertIn('Finesse',r[m['equipment']].fields['Weapon Properties'])

    def test_spell_slot_parameter_order_matches_native_upcast(self):
        p=Plan(mode='modify_existing',base_equipment=FIRST_BLOOD,user_goal='消耗三级法术位',effects=[{'kind':'grant_spell','id':'spell','base_spell':'Target_HealingWord','spell_slot':{'level':3,'amount':1}}])
        _,m,r=self.render(p)
        self.assertEqual(r[m['effect_ids']['spell']].fields['UseCosts'],self.r['records']['Target_HealingWord_3']['effective']['UseCosts'])

    def test_passive_copy_replaces_only_equipment_reference(self):
        p=Plan(mode='modify_existing',base_equipment=FIRST_BLOOD,user_goal='改词条名称',removed_original_passives=[OLD_PASSIVE],effects=[{'kind':'passive_copy','id':'copy','base_passive':OLD_PASSIVE,'display':{'name':'独立词条名'}}])
        _,m,r=self.render(p)
        self.assertNotIn(OLD_PASSIVE,r)
        self.assertEqual(r[m['effect_ids']['copy']].fields['StatsFunctors'],self.r['records'][OLD_PASSIVE]['effective']['StatsFunctors'])
        self.assertNotIn(OLD_PASSIVE,r[m['equipment']].fields['PassivesOnEquip'])

    def test_incompatible_appearance_rejected(self):
        p=example('create_new');p.appearance_equipment=FIRST_BLOOD
        self.assertTrue(validate_plan(p,self.c,self.r))

    def test_icon_selection(self):
        p=example('create_new');p.icon=self.r['templates'][LONGSWORD[10:]]['effective']['Icon']['value']
        f,_,_=self.render(p)
        root=ET.fromstring(next(v for path,v in f.items() if path.name=='_merged.lsx'))
        self.assertEqual(root.find('.//attribute[@id="Icon"]').get('value'),p.icon)

    def test_compatible_appearance_selection(self):
        p=example('create_new');p.appearance_equipment='equipment:3fc2ba50-3070-4caa-abe8-3bf885969bde'
        f,_,_=self.render(p)
        root=ET.fromstring(next(v for path,v in f.items() if path.name=='_merged.lsx'))
        expected=self.r['templates'][p.appearance_equipment[10:]]['effective']['VisualTemplate']['value']
        self.assertEqual(root.find('.//attribute[@id="VisualTemplate"]').get('value'),expected)

    def test_failed_retry_keeps_identity_and_audit(self):
        p=example('create_new');d=Draft(p)
        with tempfile.TemporaryDirectory() as out:
            for _ in range(2):
                self.assertEqual(d.review(self.c,self.r),[])
                d.confirm(expected_revision=d.revision,expected_digest=digest(p))
                with patch('scripts.crafting_compiler_v11.run_tool',side_effect=RuntimeError('conversion failure')):
                    with self.assertRaises(RuntimeError):generate_draft(d,MODULE,Path(out),catalog=self.c,resources=self.r)
                self.assertEqual(d.state,'failed')
            outputs=list(Path(out).rglob('Weapon.txt'))
            self.assertEqual(len(outputs),2)
            self.assertEqual(outputs[0].read_bytes(),outputs[1].read_bytes())
            self.assertEqual(len(list(Path(out).rglob('result.json'))),2)

if __name__=='__main__':unittest.main()
