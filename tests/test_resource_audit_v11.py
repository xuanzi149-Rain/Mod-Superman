import copy
import unittest
from backend.crafting_v11 import Plan, Draft, digest, check_resource_links
from scripts.equipment_catalog import load_catalog
from scripts.generate_equipment import FIRST_BLOOD
from scripts.resource_audit_v11 import calls, audit_expression


class ResourceAuditTests(unittest.TestCase):
    def test_nested_quoted_and_target_status(self):
        refs = {'BURNING': {'type': 'StatusData'}, 'Spell': {'type': 'SpellData'}}
        result = audit_expression("IF(HasStatus('BURNING')):ApplyStatus(SELF,BURNING,100,2);UnlockSpell(Spell)", refs)
        self.assertEqual(len(result['references']), 3)
        self.assertTrue(all(r['valid'] for r in result['references']))
        self.assertIn('unreviewed_function:IF', result['unresolved'])

    def test_missing_wrong_type_and_unknown_block(self):
        self.assertEqual(audit_expression('ApplyStatus(X,100,1)', {})['status'], 'blocked')
        self.assertEqual(audit_expression('UnlockSpell(X)', {'X': {'type': 'StatusData'}})['status'], 'blocked')
        self.assertEqual(audit_expression('ExecuteAnything()', {})['status'], 'blocked')
        self.assertEqual(audit_expression('garbage', {})['status'], 'blocked')
        self.assertEqual(audit_expression('ApplyStatus(X', {})['status'], 'blocked')

    def test_nested_commas(self):
        parsed = calls('Outer(Inner(1,2),"a,b",3)')
        self.assertEqual(parsed[-1], ('Outer', ['Inner(1,2)', '"a,b"', '3']))

    def test_status_dependency_contract(self):
        payload = dict(mode='create_new', base_equipment=FIRST_BLOOD, user_goal='test')
        status = dict(kind='independent_status', id='s1', base_status='BURNING', display={'name':'test'},
                      duration_turns=2, stacking='replace', ability='Strength', amount=2)
        trigger = dict(kind='trigger', id='e1', event='on_hit', condition='always', target='target',
                       status_draft_id='s1', duration_turns=2)
        Plan(**payload, effects=[status, trigger])
        for effects in ([status], [trigger], [status, trigger | {'duration_turns': 3}],
                        [status, trigger | {'status_ref': 'BURNING'}]):
            with self.assertRaises(ValueError):
                Plan(**payload, effects=effects)

    def test_resource_types_and_mode_rules(self):
        plan = Plan(mode='create_new', base_equipment=FIRST_BLOOD, user_goal='test',
                    parameters={'armor_class': 20}, acquisition='unknown',
                    effects=[{'kind':'grant_spell','id':'e1','base_spell':'Wrong'}],
                    removed_original_passives=['absent'])
        resources = {'records': {'Base': {'type':'Weapon','effective':{}}, 'Wrong': {'type':'StatusData'}},
                     'templates': {FIRST_BLOOD.removeprefix('equipment:'):
                         {'stats':'Base','create_eligibility':{'status':'blocked'}}}, 'acquisition_entries':[]}
        errors = check_resource_links(plan, resources)
        self.assertEqual(len(errors), 5)

    def test_catalog_change_invalidates_confirmation(self):
        catalog = load_catalog()
        draft = Draft(Plan(mode='modify_existing', base_equipment=FIRST_BLOOD,
                           user_goal='test', parameters={'damage':'2d6'}))
        draft.review(catalog)
        draft.confirm(expected_revision=1, expected_digest=digest(draft.plan))
        updated = copy.deepcopy(catalog)
        updated['items'][FIRST_BLOOD]['original']['Damage'] = '1d8'
        with self.assertRaises(ValueError):
            draft.begin_generation(updated)

    def test_slot_cost_bounds_and_text(self):
        payload = dict(mode='modify_existing', base_equipment=FIRST_BLOOD, user_goal='test')
        with self.assertRaises(ValueError):
            Plan(**payload, display={'name':'\n'})
        with self.assertRaises(ValueError):
            Plan(**payload, effects=[{'kind':'grant_spell','id':'e1','base_spell':'X',
                                    'spell_slot':{'level':7}}])

    def test_bool_revision_is_not_an_integer_revision(self):
        plan = Plan(mode='modify_existing', base_equipment=FIRST_BLOOD, user_goal='test', parameters={'damage':'2d6'})
        draft = Draft(plan)
        with self.assertRaises(ValueError):
            draft.replace(plan, source='ai', expected_revision=True)
        draft.review(load_catalog())
        with self.assertRaises(ValueError):
            draft.confirm(expected_revision=True, expected_digest=digest(plan))


if __name__ == '__main__':
    unittest.main()
