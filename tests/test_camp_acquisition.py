import unittest
import uuid
import xml.etree.ElementTree as ET
from backend.crafting_v11 import Plan
from scripts.camp_acquisition_v11 import rewards_xml,check_rewards,reward_id

class CampRewardTests(unittest.TestCase):
    def test_stable_reward_and_template_binding(self):
        module=str(uuid.uuid4());template=str(uuid.uuid4())
        data=rewards_xml(module,template)
        self.assertEqual(data,rewards_xml(module,template))
        self.assertNotEqual(reward_id(module),reward_id(str(uuid.uuid4())))
        check_rewards(data,module,template)
        with self.assertRaises(ValueError):check_rewards(data,module,str(uuid.uuid4()))
        root=ET.fromstring(data)
        self.assertEqual({a.get('id') for a in root.findall('.//attribute')},{'Amount','UUID','ItemTemplateId'})
        root.find('.//attribute[@id="Amount"]').set('value','2')
        with self.assertRaises(ValueError):check_rewards(ET.tostring(root),module,template)

    def test_default_and_legacy_migration(self):
        for entry in (None,'dammon_act1','camp_chest'):
            p=Plan(mode='create_new',base_equipment='equipment:test',user_goal='测试',acquisition=entry)
            self.assertEqual(p.acquisition,'camp_chest')
        p=Plan(mode='modify_existing',base_equipment='equipment:test',user_goal='测试')
        self.assertIsNone(p.acquisition)
        with self.assertRaises(ValueError):
            Plan(mode='modify_existing',base_equipment='equipment:test',user_goal='测试',acquisition='camp_chest')
