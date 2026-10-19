import copy
import json
import unittest
from backend.crafting_v11 import Plan
from backend.task8 import Task8Session, facts
from backend.task8_protocol import validate_output, examples
from scripts.crafting_compiler_v11 import load_resources, render_plan, validate_plan, check_files
from scripts.equipment_catalog import load_catalog, parse_stats

TEXT='装备后自己的任意武器的攻击伤害增加1d4，命中时触发，火焰伤害'
MODULE='ba8908da-5806-4eed-a55e-d098142c21ba'

class WeaponDamageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=load_resources();cls.c=load_catalog()
        cls.ring=next(k for k,v in cls.c['items'].items() if v['display_name']=='轻声承诺')

    def plan(self,base=None,mode='modify_existing'):
        return Plan(mode=mode,base_equipment=base or self.ring,user_goal=TEXT,
                    display={'name':'测试戒指'} if mode=='create_new' else {},
                    acquisition='dammon_act1' if mode=='create_new' else None,
                    effects=[{'kind':'weapon_damage','id':'fire','dice':'1d4','damage_type':'Fire'}])

    def test_native_evidence(self):
        self.assertEqual(self.r['records']['MAG_Acid_AcidDamageOnWeaponAttack_Ring_Passive']['effective']['Boosts'],'CharacterWeaponDamage(2, Acid)')
        self.assertTrue(any('CharacterWeaponDamage(1d4,' in v['effective'].get('Boosts','') for v in self.r['records'].values()))

    def test_modify_and_create_equipment(self):
        bases=[self.ring]
        for category in ('amulet','armor','weapon'):
            candidates=[k for k,v in self.c['items'].items() if v['category']==category and self.r.get('body_template_audit',{}).get('templates',{}).get(k.removeprefix('equipment:'),{}).get('qualified')]
            if candidates:bases.append(candidates[0])
        self.assertGreaterEqual(len(bases),3)
        for base in bases:
            for mode in ('modify_existing','create_new'):
                with self.subTest(base=base,mode=mode):
                    p=self.plan(base,mode)
                    if mode=='create_new':p.template_behavior='preserve_reviewed'
                    self.assertEqual(validate_plan(p,self.c,self.r),[])
                    files,m=render_plan(p,MODULE,catalog=self.c,resources=self.r)
                    check_files(files,m,self.r)
                    records={s.name:s for path,b in files.items() if path.parent.name=='Data' for s in parse_stats(b.decode(),str(path))}
                    effect=records[m['effect_ids']['fire']].fields
                    self.assertEqual(effect['Boosts'],'CharacterWeaponDamage(1d4,Fire)')
                    self.assertEqual(effect['Properties'],'IsHidden')
                    self.assertNotIn('StatsFunctors',effect)
                    self.assertIn(m['effect_ids']['fire'],records[m['equipment']].fields['PassivesOnEquip'])
                    original=self.r['records'][self.r['templates'][base.removeprefix('equipment:')]['stats']]['effective'].get('PassivesOnEquip','')
                    for ref in filter(None,original.split(';')):self.assertIn(ref,records[m['equipment']].fields['PassivesOnEquip'])

    def test_weapon_only_rules_unchanged_and_values_bounded(self):
        p=self.plan();p.parameters.damage='1d4'
        self.assertIn('parameters.damage:requires_weapon',validate_plan(p,self.c,self.r))
        p=self.plan();p.effects=[]
        payload=p.model_dump();payload['effects']=[{'kind':'trigger','id':'hit','event':'on_hit','condition':'always','target':'target','action':'damage','dice':'1d4','damage_type':'Fire','duration_turns':1}]
        self.assertIn('effects.hit:weapon_hit_requires_weapon',validate_plan(Plan.model_validate(payload),self.c,self.r))
        for extra in ({'dice':'1d99'},{'damage_type':'unknown'},{'target':'allies'},{'duration_turns':2}):
            payload=self.plan().model_dump();payload['effects'][0].update(extra)
            with self.assertRaises(ValueError):Plan.model_validate(payload)

    def test_parse_apply_update_remove_and_review_facts(self):
        p=self.plan();p.effects=[];s=Task8Session(p,self.c,self.r,inheritance='retain_base')
        def apply(kind,target,payload,text):
            c=s.context(text,'request_'+str(s.draft.revision))
            o=copy.deepcopy(examples()['parse_examples'][0]['expected_output']);o.update(c['request'])
            o['intent_summary']=text
            o['requirements']=[{'id':'r','quote':text,'meaning':text,'operation_ids':['op'],'issue_ids':[],'text_request_ids':[],'issue_update_ids':[],'no_change':False}]
            o['operations']=[{'id':'op','kind':kind,'target':target,'payload':payload,'group_id':'g','requirement_ids':['r']}]
            o['issues']=[];o['issue_updates']=[];o['text_requests']=[]
            s.apply(validate_output('parse',o,c),c)
        apply('add_effect','fire',{'effect':{'kind':'weapon_damage','dice':'1d4','damage_type':'Fire'}},TEXT)
        self.assertEqual(len(s.draft.plan.effects),1)
        e=s.draft.plan.effects[0]
        f=next(x for x in facts(s.draft.plan,self.c,self.r) if x['owner']==e.id)
        self.assertIn('任意武器',f['dimensions']['scope'])
        apply('update_effect',e.id,{'effect_kind':'weapon_damage','changes':{'dice':'2d4'}},'改成2d4')
        self.assertEqual(s.draft.plan.effects[0].dice,'2d4')
        apply('remove_effect',e.id,{},'取消该伤害加成')
        self.assertEqual(s.draft.plan.effects,[])

if __name__=='__main__':unittest.main()
