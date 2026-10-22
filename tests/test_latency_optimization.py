import copy,unittest
from backend.request_routing import simple_parameter_request,catalog_answer
from backend.task8_protocol import validate_output,examples,messages
from backend.crafting_v11 import Plan
class LatencyTests(unittest.TestCase):
 def context(self,text):return {'latest_message':{'text':text},'intent_state':{'open_issues':[]}}
 def test_full_match(self):
  for text in ['名字改为 Fool','重量改为0','重量改为0，稀有度改为稀有']:self.assertTrue(simple_parameter_request(self.context(text)))
  for text in ['重量改为0，命中回血','名字改为 Fool 并增加1d4火焰伤害','可以改哪些参数','重量改为0，其他按上次说的']:self.assertFalse(simple_parameter_request(self.context(text)))
 def test_normalize_optional_only(self):
  e=examples()['parse_examples'][0];o=copy.deepcopy(e['expected_output']);o['assistant_response']=None
  fixed=validate_output('parse',o,e['input']);self.assertNotIn('assistant_response',fixed);self.assertEqual(fixed['operations'],o['operations'])
  o['assistant_response']=123
  with self.assertRaises(ValueError):validate_output('parse',o,e['input'])
 def test_mixed_question_never_routed(self):
  self.assertIsNone(catalog_answer('可以改哪些参数，重量改为0',None,None))
 def test_wire_preserves_intent(self):
  e=examples()['parse_examples'][0];c=copy.deepcopy(e['input']);c['latest_message']['text']='重量改为0';original=copy.deepcopy(c)
  import json
  wire=json.loads(messages('parse',c)[-1]['content']);self.assertEqual(wire['latest_message'],c['latest_message']);self.assertEqual(wire['current_plan'],c['current_plan']);self.assertEqual(wire['effective_values'],c['effective_values']);self.assertEqual(c,original)
