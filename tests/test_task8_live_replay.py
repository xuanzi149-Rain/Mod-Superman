import copy
import json
import unittest
from unittest.mock import patch
from backend.task8_protocol import Task8Model, validate_output
from backend.player_language import player_issue
from scripts.generate_mod import ROOT

class LiveRecoveryReplayTests(unittest.TestCase):
    def test_three_real_outputs_replay_without_network(self):
        evidence=json.loads((ROOT/'docs/v1.1/task8/v9-live-results.json').read_text(encoding='utf-8'))
        for row in evidence['results']:
            with self.subTest(text=row['input']):
                call=row['calls'][0]
                with patch.object(Task8Model,'parse',return_value=(copy.deepcopy(call['output']),call['usage'])) as mocked:
                    output, usage=Task8Model().run('parse',row['context'])
                self.assertEqual(mocked.call_count,1)
                validate_output('parse',output,row['context'])
                if '增加1' in row['input']:
                    self.assertEqual(output['operations'],[])
                    issue=output['issues'][0]
                    self.assertEqual(issue['kind'],'clarification')
                    self.assertIn('固定伤害',issue['question'])
                    self.assertEqual(len(issue['options']),3)
                    self.assertNotIn('damage',issue['detail'])
                    self.assertNotIn('协议',issue['detail'])
                else:
                    self.assertFalse(output['issues'])

    def test_implementation_explanation_does_not_become_resource_lookup(self):
        issue={'kind':'clarification','detail':'协议不允许 damage 字段。','question':'增加固定伤害还是改变骰子？','options':[],'evidence_refs':[]}
        output=player_issue(issue)
        self.assertEqual(output['kind'],'clarification')
        self.assertEqual(output['question'],issue['question'])
        self.assertNotIn('damage',output['detail'])

    def test_saved_live_results_change_only_requested_parameters(self):
        evidence=json.loads((ROOT/'docs/v1.1/task8/v9-live-results.json').read_text(encoding='utf-8'))
        self.assertLessEqual(evidence['calls_started'],6)
        for index,row in enumerate(evidence['results']):
            self.assertNotIn('error',row)
            before=copy.deepcopy(row['before']); after=copy.deepcopy(row['after'])
            before.pop('unresolved'); after.pop('unresolved')
            if index==1: before['parameters']['damage']='2d6'
            if index==2: before['parameters']['weight_kg']=0.45
            self.assertEqual(after,before)
        recheck=evidence['retests'][0]
        self.assertNotIn('error',recheck)
        self.assertTrue(recheck['issues'])
        self.assertEqual(recheck['after']['parameters'],evidence['results'][0]['before']['parameters'])
        for issue in recheck['issues']:
            self.assertNotIn('协议',issue['detail'])
            self.assertNotIn('damage',issue['detail'])

if __name__=='__main__': unittest.main()
