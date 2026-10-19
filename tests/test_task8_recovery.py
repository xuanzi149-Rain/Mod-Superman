import copy
import unittest
from unittest.mock import patch
from backend.task8_protocol import Task8Model, examples, validate_output, recovery_issue
from backend.service import ServiceError

class RecoveryTests(unittest.TestCase):
    def fixture(self, task='parse'):
        e = examples()[task+'_examples'][0]
        return copy.deepcopy(e['input']), copy.deepcopy(e['expected_output'])

    def test_reported_damage_operation_is_corrected_before_return(self):
        c, good = self.fixture()
        bad = copy.deepcopy(good)
        bad['operations'][0].update(kind='relative_parameter', target='damage',
            payload={'operator':'add','operand':1,'basis':'current','unit':None})
        with patch.object(Task8Model, 'parse', side_effect=[(bad, {'total_tokens':10}), (good, {'total_tokens':20})]) as call:
            result, usage = Task8Model().run('parse', c)
        self.assertEqual(result, good)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(usage['total_tokens'], 30)
        self.assertEqual(usage['recovery'], 'corrected')
        self.assertIn('schema:operations/0', call.call_args.args[0]['repair']['validation_error'])
        self.assertEqual(call.call_args.args[0]['context'], c)

    def test_exhaustion_preserves_every_word_without_applying_partial_changes(self):
        c, good = self.fixture()
        bad = copy.deepcopy(good); bad['operations'][0]['kind']='invented'
        with patch.object(Task8Model, 'parse', return_value=(bad, None)) as call:
            result, usage = Task8Model().run('parse', c)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(result['operations'], [])
        self.assertEqual(result['requirements'][0]['quote'], c['latest_message']['text'])
        self.assertEqual(usage['recovery'], 'pending_requirement')
        validate_output('parse', result, c)

    def test_invalid_json_is_retried(self):
        c, good = self.fixture()
        with patch.object(Task8Model, 'parse', side_effect=[ServiceError('model_invalid_output','bad',502),(good,None)]):
            self.assertEqual(Task8Model().run('parse',c)[0], good)

    def test_stale_context_and_network_are_not_retried(self):
        c, good = self.fixture(); good['base_revision'] += 1
        with patch.object(Task8Model,'parse',return_value=(good,None)) as call:
            with self.assertRaisesRegex(ValueError,'stale_context'): Task8Model().run('parse',c)
        self.assertEqual(call.call_count,1)
        with patch.object(Task8Model,'parse',side_effect=ServiceError('model_timeout','timeout',504)) as call:
            with self.assertRaises(ServiceError): Task8Model().run('parse',c)
        self.assertEqual(call.call_count,1)

    def test_review_repair_and_exhaustion_cannot_approve_text(self):
        c, good = self.fixture('review')
        with patch.object(Task8Model,'parse',side_effect=[({},None),(good,None)]):
            self.assertEqual(Task8Model().run('review',c)[0],good)
        with patch.object(Task8Model,'parse',return_value=({},None)) as call:
            with self.assertRaises(ServiceError) as error: Task8Model().run('review',c)
        self.assertEqual(error.exception.code,'model_review_unresolved')
        self.assertEqual(call.call_count,2)

    def test_long_input_preserved(self):
        c, _ = self.fixture(); c['latest_message']['text']='修改装备'*1000
        validate_output('parse', recovery_issue(c), c)

if __name__ == '__main__': unittest.main()
