import copy
import unittest
from scripts.body_template_audit_v11 import weapon_visual_issues
from scripts.crafting_compiler_v11 import load_resources, validate_plan
from scripts.equipment_catalog import load_catalog
from backend.crafting_v11 import Plan, check_resource_links

KEY='025e162a-45ec-4f4c-89da-04d8e8dfe606'

class WeaponIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources=load_resources();cls.catalog=load_catalog()

    def test_kings_knife_uses_current_index_despite_historical_failure(self):
        r=self.resources;t=r['templates'][KEY]
        self.assertEqual(t['create_eligibility']['status'],'blocked')
        self.assertTrue(r['body_template_audit']['templates'][KEY]['qualified'])
        p=Plan(mode='create_new',base_equipment='equipment:'+KEY,user_goal='仅创建改名副本',display={'name':'地脉匕首副本'},acquisition='dammon_act1')
        self.assertEqual(validate_plan(p,self.catalog,r),[])
        self.assertEqual(check_resource_links(p,r),[])
        from backend.task8 import facts
        evidence=facts(p,self.catalog,r)
        self.assertTrue(all(not f['missing'] for f in evidence),evidence)
        inherited=evidence[0]['dimensions']['inherited_dependencies']
        self.assertEqual(inherited['MAG_TheClover_Rearrangement_Passive'],r['records']['MAG_TheClover_Rearrangement_Passive']['effective'])
        self.assertEqual(inherited['ShadowBlade_Passive'],r['records']['ShadowBlade_Passive']['effective'])

    def test_current_visual_gate_still_rejects_missing_files_icons_and_remapping(self):
        t=self.resources['templates'][KEY];ref=t['effective']['VisualTemplate']['value']
        visual=copy.deepcopy(self.resources['body_template_audit']['visuals'][ref])
        models={visual['SourceFile'].casefold()};icons=self.resources['icon_asset_validation']
        self.assertEqual(weapon_visual_issues(t,{ref:visual},models,icons),[])
        self.assertIn('visual_model_not_verified',weapon_visual_issues(t,{},models,icons))
        self.assertIn('visual_model_not_verified',weapon_visual_issues(t,{ref:visual},set(),icons))
        self.assertIn('icon_atlas_not_verified',weapon_visual_issues(t,{ref:visual},models,{}))
        for change in ({'NeedsSkeletonRemap':'True'},{'SkeletonResource':'unknown-skeleton'},{'NeedsSkeletonRemap':None}):
            with self.subTest(change=change):
                self.assertIn('skeleton_mapping_not_reviewed',weapon_visual_issues(t,{ref:{**visual,**change}},models,icons))

    def test_new_audit_rejection_cannot_fall_back_to_old_approval(self):
        r=dict(self.resources);audit=dict(r['body_template_audit']);audit['templates']=dict(audit['templates'])
        r['templates']=dict(r['templates'])
        r['templates'][KEY]={**r['templates'][KEY],'create_eligibility':{'status':'base_template_qualified'}}
        audit['templates'][KEY]={**audit['templates'][KEY],'qualified':False,'issues':['visual_model_not_verified']}
        r['body_template_audit']=audit
        p=Plan(mode='create_new',base_equipment='equipment:'+KEY,user_goal='不能绕过',display={'name':'测试'},acquisition='dammon_act1')
        self.assertIn('base_equipment:unqualified_visual',check_resource_links(p,r))
        self.assertIn('base_equipment:visual_model_not_verified',validate_plan(p,self.catalog,r))
