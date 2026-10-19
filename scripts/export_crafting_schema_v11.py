"""Export the versioned draft contract and reproducible request examples."""
import json
from backend.crafting_v11 import Plan, BaseParameters, WeaponDamageBonus, ConstantEffect, TriggerEffect, GrantedSpell, IndependentStatus, NativeBonus, PassiveCopy
from scripts.equipment_catalog import ROOT
from scripts.generate_equipment import FIRST_BLOOD


if __name__ == '__main__':
    output = ROOT / 'data/v1.1'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'plan.schema.json').write_text(json.dumps(Plan.model_json_schema(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    examples = [
        Plan(mode='modify_existing', base_equipment=FIRST_BLOOD, user_goal='短剑伤害改为2d6', parameters={'damage': '2d6'}),
        Plan(mode='create_new', base_equipment='equipment:1865323f-b428-4791-a0a9-578841e57463', user_goal='独立长剑，装备后力量加2',
             display={'name':'独立长剑'}, acquisition='dammon_act1', effects=[{'kind': 'constant', 'id': 'effect-1', 'ability': 'Strength', 'amount': 2}]),
    ]
    (output / 'plan-examples.json').write_text(json.dumps([e.model_dump(mode='json') for e in examples], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    capabilities = json.loads((output / 'capabilities.json').read_text(encoding='utf-8'))
    capabilities['contract_version'] = '1.1-draft-4'
    capabilities['contract_schemas'] = {cls.__name__: cls.model_json_schema() for cls in
                                         (BaseParameters, WeaponDamageBonus, ConstantEffect, NativeBonus, PassiveCopy, TriggerEffect, GrantedSpell, IndependentStatus)}
    capabilities['rules_document'] = 'docs/v1.1/能力规则与阶段边界.md'
    capabilities['resource_policy'] = {'new_equipment': 'audited native weapon/armor/shield/jewelry template with complete inheritance',
                                       'armor_creation': '25 native EquipmentRace profiles resolved through native fallbacks; visual and model paths verified',
                                       'special_templates': 'reviewed native actions and tags require explicit preserve_reviewed acknowledgement; unknown behavior rejected',
                                       'native_dependencies': 'typed acyclic copies including statuses, subspells, containers, upcasts and AI variants; predicates and immunity retain native targets',
                                       'unknown_expressions': 'blocked',
                                       'honour': 'separate effective diff, preserve unless explicitly changed',
                                       'acquisition': 'dammon_act1 local entity/table verified; refresh unverified'}
    capabilities['phase_b_implementation'] = {'compiler': 'scripts/crafting_compiler_v11.py', 'status': 'acceptance_passed', 'acceptance': 'docs/v1.1/phase-b-acceptance.json', 'rules': 'docs/v1.1/阶段B执行记录.md', 'legacy_entries': 'A-stage assessment retained below; use compiler validation for current executable support', 'remaining': [], 'next_phase': ['phase C website and AI integration and custom description review']}
    for entry in capabilities['entries']:
        if entry['id'] != 'custom_scripts_and_new_art':
            entry.setdefault('phase_a_assessment', entry['assessment'])
            entry['assessment'] = 'implemented_for_validated_profiles'
            entry['implementation'] = 'scripts/crafting_compiler_v11.py'
            entry['current_rule_reference'] = 'docs/v1.1/阶段B执行记录.md'
    (output / 'capabilities.json').write_text(json.dumps(capabilities, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
