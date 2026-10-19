import unittest
from pydantic import ValidationError
from backend.crafting_v11 import Plan, Draft, digest, edit_effect, restore_parameter
from scripts.equipment_catalog import load_catalog, parse_stats, add_stats, resolve_stat, resolve_root
from scripts.generate_equipment import FIRST_BLOOD


class CraftingTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.plan = Plan(mode='modify_existing', base_equipment=FIRST_BLOOD,
                         user_goal='修改短剑', parameters={'damage': '2d6'})

    def confirmed(self):
        draft = Draft(self.plan)
        self.assertEqual(draft.review(self.catalog), [])
        draft.confirm(expected_revision=1, expected_digest=digest(draft.plan))
        return draft

    def test_edit_invalidates_confirmation_for_both_sources(self):
        for source in ('manual', 'ai'):
            draft = self.confirmed()
            changed = draft.plan
            changed.display.description = 'new text'
            draft.replace(changed, source=source, expected_revision=1)
            with self.assertRaises(ValueError):
                draft.begin_generation(self.catalog)
            self.assertIsNone(draft.confirmation)

    def test_stale_and_unreviewed_confirmation(self):
        draft = Draft(self.plan)
        with self.assertRaises(ValueError):
            draft.confirm(expected_revision=1, expected_digest=digest(draft.plan))
        draft.review(self.catalog)
        with self.assertRaises(ValueError):
            draft.confirm(expected_revision=2, expected_digest=digest(draft.plan))

    def test_unavailable_effect_and_create_fail_closed(self):
        for patch in ({'mode': 'create_new'}, {'effects': [{'kind': 'constant', 'id': 'e1', 'ability': 'Strength', 'amount': 2}]}):
            draft = Draft(Plan.model_validate(self.plan.model_dump() | patch))
            self.assertTrue(draft.review(self.catalog))
            with self.assertRaises(ValueError):
                draft.confirm(expected_revision=1, expected_digest=digest(draft.plan))

    def test_copies_and_running_edit(self):
        draft = self.confirmed()
        copy = draft.plan
        copy.user_goal = 'changed'
        self.assertNotEqual(draft.plan.user_goal, copy.user_goal)
        draft.begin_generation(self.catalog)
        with self.assertRaises(ValueError):
            draft.replace(copy, source='ai', expected_revision=1)
        draft.finish(success=False, failure_reason='packaging_error')
        self.assertEqual(draft.state, 'failed')

    def test_effect_operations_do_not_remove_native_passive(self):
        draft = Draft(self.plan)
        effect = {'kind': 'constant', 'id': 'e1', 'ability': 'Strength', 'amount': 2}
        edit_effect(draft, action='add', effect_id='e1', value=effect, source='ai', expected_revision=1)
        edit_effect(draft, action='update', effect_id='e1', value=effect | {'amount': 3}, source='manual', expected_revision=2)
        edit_effect(draft, action='delete', effect_id='e1', source='manual', expected_revision=3)
        self.assertEqual(draft.plan.removed_original_passives, [])
        restore_parameter(draft, 'damage', source='manual', expected_revision=4)
        self.assertIsNone(draft.plan.parameters.damage)
        self.assertTrue(draft.review(self.catalog))

    def test_no_raw_code_unknown_fields_or_duplicate_ids(self):
        with self.assertRaises(ValidationError):
            Plan.model_validate(self.plan.model_dump() | {'code': 'print(1)'})
        effect = {'kind': 'constant', 'id': 'e1', 'ability': 'Strength', 'amount': 2}
        with self.assertRaises(ValidationError):
            Plan.model_validate(self.plan.model_dump() | {'effects': [effect, effect]})

    def test_new_base_parameters_cannot_bypass_gate(self):
        payload = self.plan.model_dump()
        payload['parameters']['armor_class'] = 20
        draft = Draft(Plan.model_validate(payload))
        self.assertIn('parameter_not_implemented:armor_class', draft.review(self.catalog))

    def test_inheritance_failures_and_self_override(self):
        stats = {}
        add_stats(stats, parse_stats('new entry "A"\ntype "Weapon"\ndata "Damage" "1d6"', 'base'))
        add_stats(stats, parse_stats('new entry "A"\ntype "Weapon"\nusing "A"\ndata "Weight" "1"', 'override'))
        self.assertEqual(resolve_stat('A', stats)[0], {'Damage': '1d6', 'Weight': '1'})
        for text in ('new entry "B"\ntype "Weapon"\nusing "Missing"',
                     'new entry "B"\ntype "Weapon"\nusing "C"\nnew entry "C"\ntype "Weapon"\nusing "B"'):
            broken = {}
            add_stats(broken, parse_stats(text, 'test'))
            with self.assertRaises(ValueError):
                resolve_stat('B', broken)
        with self.assertRaises(ValueError):
            resolve_root('A', {'A': {'ParentTemplateId': {'value': 'A'}}})


if __name__ == '__main__':
    unittest.main()
