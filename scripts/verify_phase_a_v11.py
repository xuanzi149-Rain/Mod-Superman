"""Verify phase-A deliverables against the real local catalog; does not build mods."""
import hashlib
import json
from pathlib import Path
from backend.crafting_v11 import Plan, Draft, digest, check_capabilities
from scripts.equipment_catalog import ROOT, load_catalog
from scripts.generate_equipment import FIRST_BLOOD


def verify():
    from scripts.crafting_compiler_v11 import load_resources
    resources = load_resources()
    for path, expected in resources['inputs_sha256'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    assert not resources['honour']['errors']
    template = resources['templates'][FIRST_BLOOD.removeprefix('equipment:')]
    assert template['create_eligibility']['status'] == 'base_template_qualified'
    entry = resources['acquisition_entries'][0]
    assert entry['npc_mapping']['matched']
    assert 'DefaultBoosts' in resources['honour']['differences'][template['stats']]
    assert template['effective_field_sources']['VisualTemplate']
    assert not template['create_eligibility']['generation_ready']
    catalog = load_catalog()
    examples = json.loads((ROOT / 'data/v1.1/plan-examples.json').read_text(encoding='utf-8'))
    outcomes = []
    for example in examples:
        plan = Plan.model_validate(example)
        issues = check_capabilities(plan, catalog, resources)
        outcomes.append({'mode':plan.mode, 'issues':issues})
        if plan.mode == 'create_new':
            assert issues == [], issues  # B now compiles the qualified ordinary weapon example.
    first = Draft(Plan.model_validate(examples[0]))
    assert first.review(catalog, resources) == []
    first.confirm(expected_revision=1, expected_digest=digest(first.plan))
    # Gate only; no output, package, server or game is started.
    first.begin_generation(catalog, resources)
    result = {'status':'passed', 'source_files_verified':len(resources['inputs_sha256']),
              'stats_records':sum(resources['counts'].values()),
              'honour_changes':len(resources['honour']['differences']),
              'qualified_base_templates':sum(t['create_eligibility']['status']=='base_template_qualified'
                                              for t in resources['templates'].values()),
              'native_acquisition':entry['npc_mapping'], 'examples':outcomes,
              'generation_performed':False, 'game_validation':'not_performed'}
    (ROOT / 'docs/v1.1/phase-a-acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    verify()
