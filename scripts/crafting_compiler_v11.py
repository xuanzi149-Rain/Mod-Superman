"""Deterministic phase B compiler. Native expressions are emitted only by typed rules."""
from scripts.camp_acquisition_v11 import ENTRY, rewards_xml, check_rewards
from decimal import Decimal
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import uuid
import xml.etree.ElementTree as ET

from backend.crafting_v11 import Plan, ConstantEffect, NativeBonus, WeaponDamageBonus, PassiveCopy, TriggerEffect, IndependentStatus, GrantedSpell, digest
from scripts.generate_mod import ROOT, DIVINE, localization, run_tool
from scripts.generate_equipment import FIRST_BLOOD
from scripts.native_dependencies_v11 import closure, spell_profile, rewrite_refs, replace_amount

ABILITIES = {'Strength', 'Dexterity', 'Constitution', 'Intelligence', 'Wisdom', 'Charisma'}
SKILLS = {'Athletics', 'Acrobatics', 'SleightOfHand', 'Stealth', 'Arcana', 'History', 'Investigation', 'Nature', 'Religion', 'AnimalHandling', 'Insight', 'Medicine', 'Perception', 'Survival', 'Deception', 'Intimidation', 'Performance', 'Persuasion'}
DAMAGE_TYPES = {'Slashing', 'Piercing', 'Bludgeoning', 'Acid', 'Cold', 'Fire', 'Force', 'Lightning', 'Necrotic', 'Poison', 'Psychic', 'Radiant', 'Thunder'}
OLD_PASSIVE = 'UND_Duergar_ShortswordOfFirstBlood_Passive'
FIELD_MAP = {'damage': 'Damage', 'versatile_damage': 'VersatileDamage', 'weight_kg': 'Weight', 'rarity': 'Rarity', 'armor_class': 'ArmorClass', 'value': 'ValueOverride', 'damage_type': 'Damage Type'}


def load_resources():
    resources = json.loads((ROOT / 'build/v1.1/resource-catalog.json').read_text(encoding='utf-8'))
    for path, expected in resources['inputs_sha256'].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Resource source changed; rebuild catalog: {path}')
    audit_path = ROOT / 'build/v1.1/body-template-audit.json'
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        for path, expected in audit['inputs_sha256'].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise ValueError('Body audit source changed: ' + path)
        resources['body_template_audit'] = audit
    resources['acquisition_entries'] = [dict(ENTRY)]
    return resources


def number(value):
    return format(Decimal(str(value)), 'f')


def validate_plan(plan, catalog, resources, *, text_receipt=None):
    issues = []
    if plan.unresolved:
        issues.append('unresolved_questions')
    templates, records = resources['templates'], resources['records']
    key = plan.base_equipment.removeprefix('equipment:')
    t = templates.get(key)
    if t is None:
        return ['base_equipment:missing_template']
    base = records[t['stats']]
    fields = base['effective']
    if base['type'] not in ('Weapon', 'Armor'):
        return ['base_equipment:wrong_type']
    if plan.mode == 'modify_existing' and plan.base_equipment not in catalog['items']:
        issues.append('base_equipment:not_in_modify_catalog')
    if plan.mode == 'create_new':
        audited = resources.get('body_template_audit', {}).get('templates', {}).get(key)
        if not (audited and audited['qualified']):
            issues.append('base_equipment:unqualified_visual')
        if not plan.display.name:
            issues.append('display.name:required_for_new_equipment')
        if plan.acquisition != 'camp_chest':
            issues.append('acquisition:unknown_or_unverified')
        # A's flat template index does not inspect child nodes. Reject templates with special
        # use/story behaviour based on the original node, before inheriting it.
        if audited and audited['special_actions'] and plan.template_behavior != 'preserve_reviewed':
            issues.append('base_equipment:special_behavior_requires_acknowledgement')
        if audited and not audited['qualified']:
            issues.extend('base_equipment:' + issue for issue in audited['issues'])
    if plan.appearance_equipment:
        other_key = plan.appearance_equipment.removeprefix('equipment:')
        other = templates.get(other_key)
        audit = resources.get('body_template_audit', {}).get('templates', {}).get(other_key, {})
        if plan.mode != 'create_new' or other is None or not audit.get('qualified'):
            issues.append('appearance_equipment:unqualified')
        else:
            other_record = records[other['stats']]
            compare = ('Slot', 'Weapon Group', 'Proficiency Group') if base['type'] == 'Weapon' else ('Slot',)
            if other_record['type'] != base['type'] or any(other_record['effective'].get(f) != fields.get(f) for f in compare):
                issues.append('appearance_equipment:incompatible_equipment_family')
            if audit['special_actions'] and plan.template_behavior != 'preserve_reviewed':
                issues.append('appearance_equipment:special_behavior_requires_acknowledgement')
            base_actions = resources.get('body_template_audit', {}).get('templates', {}).get(key, {}).get('special_actions', [])
            if audit['special_actions'] != base_actions:
                issues.append('appearance_equipment:special_behavior_mismatch')
    if plan.icon and not resources['icon_asset_validation'].get(plan.icon, {}).get('asset_exists'):
        issues.append('icon:unverified_asset')
    p = plan.parameters
    for field in ('damage', 'versatile_damage', 'damage_type', 'enchantment', 'weapon_properties'):
        if getattr(p, field) is not None and base['type'] != 'Weapon':
            issues.append(f'parameters.{field}:requires_weapon')
    for field in ('armor_class', 'dexterity_rule'):
        if getattr(p, field) is not None and (base['type'] != 'Armor' or 'ArmorClass' not in fields):
            issues.append(f'parameters.{field}:requires_body_armor_or_shield')
    if p.dexterity_rule and fields.get('Shield') == 'Yes':
        issues.append('parameters.dexterity_rule:shield_not_supported')
    props = p.weapon_properties if p.weapon_properties is not None else fields.get('Weapon Properties', '').split(';')
    if p.weapon_properties is not None:
        if len(props) != len(set(props)) or ('Twohanded' in props and 'Versatile' in props):
            issues.append('parameters.weapon_properties:conflicting_or_duplicate')
        for structural in ('Melee', 'Ranged', 'Twohanded', 'Versatile', 'Thrown', 'Reach', 'Heavy'):
            if (structural in props) != (structural in fields.get('Weapon Properties', '').split(';')):
                issues.append(f'parameters.weapon_properties:{structural}_requires_resource_remap')
    if p.versatile_damage and 'Versatile' not in props:
        issues.append('parameters.versatile_damage:requires_versatile')
    if p.weight_kg is not None and Decimal(str(p.weight_kg)) != Decimal(str(p.weight_kg)).quantize(Decimal('.001')):
        issues.append('parameters.weight_kg:three_decimals_max')
    original = set(filter(None, fields.get('PassivesOnEquip', '').split(';')))
    honour = resources['honour']['differences']
    for ref in plan.removed_original_passives:
        if ref not in original:
            issues.append(f'removed_original_passives.{ref}:not_on_base')
        # Only the separately researched First Blood dual path can be removed safely.
        if (t['stats'] in honour or ref in honour) and not (plan.base_equipment == FIRST_BLOOD and ref == OLD_PASSIVE):
            issues.append(f'removed_original_passives.{ref}:honour_mapping_unreviewed')
    if p.enchantment is not None:
        if 'DefaultBoosts' in honour.get(t['stats'], {}) and not (plan.base_equipment == FIRST_BLOOD and OLD_PASSIVE in plan.removed_original_passives):
            issues.append('parameters.enchantment:honour_boost_merge_requires_explicit_resolution')
        for f in ('Boosts', 'BoostsOnEquipMainHand', 'BoostsOnEquipOffHand'):
            if 'WeaponEnchantment(' in fields.get(f, ''):
                issues.append('parameters.enchantment:additional_enchantment_source')
    if p.weapon_properties is not None and 'Magical' not in props and 'WeaponProperty(Magical)' in fields.get('DefaultBoosts', ''):
        issues.append('parameters.weapon_properties:magical_has_additional_source')
    for e in plan.effects:
        prefix = f'effects.{e.id}:'
        if isinstance(e, NativeBonus):
            allowed = SKILLS if e.bonus == 'skill' else ABILITIES if e.bonus == 'saving_throw' else DAMAGE_TYPES if e.bonus == 'resistance' else {None}
            if e.selector not in allowed:
                issues.append(prefix + 'invalid_bonus_selector')
            if e.bonus == 'resistance' and e.amount != 1:
                issues.append(prefix + 'resistance_is_not_numeric')
        elif isinstance(e, PassiveCopy):
            try:
                if records.get(e.base_passive, {}).get('type') != 'PassiveData':
                    raise ValueError('wrong_passive_type')
                closure(e.base_passive, records)
            except ValueError as error:
                issues.append(prefix + str(error))
            if e.base_passive not in plan.removed_original_passives:
                issues.append(prefix + 'copy_requires_explicit_original_replacement')
        elif isinstance(e, TriggerEffect):
            if e.event == 'on_hit' and base['type'] != 'Weapon':
                issues.append(prefix + 'weapon_hit_requires_weapon')
            if e.action == 'damage' and e.target == 'self':
                issues.append(prefix + 'self_damage_not_supported')
            if e.event != 'on_hit' and (e.target != 'self' or e.condition != 'always'):
                issues.append(prefix + 'non_hit_requires_self_and_always')
            if e.event == 'on_heal' and e.action == 'heal' or e.event == 'on_damaged' and e.action == 'damage':
                issues.append(prefix + 'recursive_trigger_risk')
            if e.status_ref:
                try:
                    refs = closure(e.status_ref, records)
                    if e.event == 'on_heal' and any('RegainHitPoints(' in str(records[r]['effective']) for r in refs):
                        raise ValueError('recursive_healing_status')
                    if e.event == 'on_damaged' and any('DealDamage(' in str(records[r]['effective']) for r in refs):
                        raise ValueError('recursive_damage_status')
                except ValueError as error:
                    issues.append(prefix + str(error))
        elif isinstance(e, IndependentStatus):
            if records.get(e.base_status, {}).get('effective', {}).get('StatusType') != 'BOOST':
                issues.append(prefix + 'independent_status_requires_BOOST_base')
            for bonus in e.bonuses:
                allowed = SKILLS if bonus.bonus == 'skill' else ABILITIES if bonus.bonus == 'saving_throw' else DAMAGE_TYPES if bonus.bonus == 'resistance' else {None}
                if bonus.selector not in allowed or bonus.bonus == 'resistance' and bonus.amount != 1:
                    issues.append(prefix + 'invalid_status_bonus:' + bonus.id)
        elif isinstance(e, GrantedSpell):
            try:
                profile = spell_profile(e.base_spell, records)
                definitions = resources.get('body_template_audit', {}).get('action_resources', {})
                for ref in closure(e.base_spell, records, True):
                    for expression in records[ref]['effective'].values():
                        for level_map in re.findall(r'LevelMapValue\(([A-Za-z0-9_]+)\)', expression):
                            if level_map not in resources.get('body_template_audit', {}).get('level_maps', {}):
                                raise ValueError('unknown_level_map:' + level_map)
                    for cost in filter(None, records[ref]['effective'].get('UseCosts', '').split(';')):
                        if cost.split(':')[0] not in definitions:
                            raise ValueError('unknown_action_resource:' + cost.split(':')[0])
                if e.spell_slot and e.remove_spell_slot:
                    raise ValueError('conflicting_spell_slot_operations')
                for parameter in ('healing', 'damage'):
                    if getattr(e, parameter) and parameter not in profile['amount_fields']:
                        raise ValueError('ambiguous_or_missing_effect:' + parameter)
                if e.status_duration_turns is not None:
                    status_duration(records[e.base_spell]['effective'].get('SpellProperties', ''), e.status_duration_turns)
                if e.area_radius_m is not None and not profile['area_field']:
                    raise ValueError('area_not_supported_by_spell_type')
                if e.range_m is not None and not profile['range_field']:
                    raise ValueError('self_centered_spell_has_no_target_range')
            except (ValueError, KeyError) as error:
                issues.append(prefix + str(error))
        ref = e.base_spell if isinstance(e, GrantedSpell) else e.base_status if isinstance(e, IndependentStatus) else e.status_ref if isinstance(e, TriggerEffect) else None
        expected = 'SpellData' if isinstance(e, GrantedSpell) else 'StatusData'
        if ref and (ref not in records or records[ref]['type'] != expected):
            issues.append(prefix + 'missing_or_wrong_type_reference')
    if not (p.model_dump(exclude_none=True) or plan.effects or plan.removed_original_passives or plan.display.model_dump(exclude_none=True) or plan.icon or plan.mode == 'create_new'):
        issues.append('empty_changes')
    return issues


def identity(namespace, label):
    return uuid.uuid5(uuid.UUID(str(namespace)), label)


def stat_record(name, kind, fields, parent=None):
    if not re.fullmatch(r'[A-Za-z0-9_]+', name) or parent and not re.fullmatch(r'[A-Za-z0-9_]+', parent):
        raise ValueError('Invalid native identifier')
    lines = [f'new entry "{name}"', f'type "{kind}"']
    if parent:
        lines.append(f'using "{parent}"')
    for k, v in fields.items():
        if any(c in str(v) for c in ('"', '\n', '\r')):
            raise ValueError(f'Unsafe Stats value: {k}')
        lines.append(f'data "{k}" "{v}"')
    return '\n'.join(lines) + '\n\n'


def bonus_expression(e):
    if isinstance(e, WeaponDamageBonus):
        return f'CharacterWeaponDamage({e.dice},{e.damage_type})'
    if isinstance(e, ConstantEffect):
        return f'Ability({e.ability},{e.amount})'
    return {'initiative': lambda: f'Initiative({e.amount})', 'movement': lambda: f'ActionResource(Movement,{e.amount},0)', 'skill': lambda: f'Skill({e.selector},{e.amount})', 'saving_throw': lambda: f'RollBonus(SavingThrow,{e.amount},{e.selector})', 'armor_class': lambda: f'AC({e.amount})', 'resistance': lambda: f'Resistance({e.selector},Resistant)'}[e.bonus]()


def spell_fields(e, source_id, records):
    source = records[source_id]['effective']
    profile = spell_profile(source_id, records)
    fields = {}
    if e.range_m is not None:
        fields['TargetRadius'] = number(e.range_m)
    if e.area_radius_m is not None:
        fields['AreaRadius'] = number(e.area_radius_m)
    costs = [v for v in source.get('UseCosts', '').split(';') if v]
    if e.action_cost is not None:
        costs = [v for v in costs if not v.startswith(('ActionPoint:', 'BonusActionPoint:'))]
        if e.action_cost != 'none':
            costs.insert(0, {'action':'ActionPoint:1', 'bonus_action':'BonusActionPoint:1'}[e.action_cost])
    if e.spell_slot or e.remove_spell_slot:
        costs = [v for v in costs if not v.startswith('SpellSlotsGroup:')]
        if e.spell_slot:
            costs.append(f'SpellSlotsGroup:{e.spell_slot.amount}:1:{e.spell_slot.level}')
    fields['UseCosts'] = ';'.join(costs)
    if e.cooldown is not None:
        fields['Cooldown'] = {'once_per_turn':'OncePerTurn','short_rest':'OncePerShortRest','long_rest':'OncePerRest','none':''}[e.cooldown]
    for parameter, function in [('healing','RegainHitPoints'),('damage','DealDamage')]:
        value = getattr(e, parameter)
        if value is not None:
            field = profile['amount_fields'][parameter]
            fields[field] = replace_amount(source[field], function, value)
            if function + '(' in source.get('TooltipDamageList', ''):
                fields['TooltipDamageList'] = replace_amount(source['TooltipDamageList'], function, value)
            fields['TooltipUpcastDescription'] = ''
            fields['TooltipUpcastDescriptionParams'] = ''
    fields['DescriptionParams'] = ''
    if e.status_duration_turns is not None:
        fields['SpellProperties'] = status_duration(fields.get('SpellProperties', source.get('SpellProperties','')), e.status_duration_turns)
        if 'ApplyStatus(' in source.get('TooltipStatusApply',''):
            fields['TooltipStatusApply'] = status_duration(source['TooltipStatusApply'], e.status_duration_turns)
    return fields


def status_duration(expression, turns):
    pattern = r'(ApplyStatus\((?:(?:SELF|TARGET|OWNER),\s*)?[A-Za-z0-9_]+,\s*100,\s*)-?\d+(\))'
    changed, count = re.subn(pattern, lambda m: m[1] + str(turns) + m[2], expression)
    if count != 1:
        raise ValueError('status_duration_requires_one_explicit_status')
    return changed


def render_plan(plan, module_id, *, catalog, resources, text_receipt=None):
    """Pure compiler; caller must use generate_draft for confirmed packaged output."""
    plan = Plan.model_validate(plan.model_dump())
    issues = validate_plan(plan, catalog, resources, text_receipt=text_receipt)
    if issues:
        raise ValueError('; '.join(issues))
    module_id = str(uuid.UUID(str(module_id)))
    module = 'ModSuperman_' + module_id
    key = plan.base_equipment.removeprefix('equipment:')
    template = resources['templates'][key]
    base_name = template['stats']
    base = resources['records'][base_name]
    original = base['effective']
    new = plan.mode == 'create_new'
    equipment_id = 'MS_' + identity(module_id, 'equipment').hex if new else base_name
    root_id = str(identity(module_id, 'template')) if new else key
    ids = {e.id: ('Target_' if isinstance(e, GrantedSpell) and e.base_spell.startswith('Target_') else 'Projectile_' if isinstance(e, GrantedSpell) and e.base_spell.startswith('Projectile_') else 'Shout_' if isinstance(e, GrantedSpell) else '') + 'MS_' + identity(module_id, 'effect:' + e.id).hex for e in plan.effects}
    texts, groups, files = [], {}, {}
    def text_handle(label, value):
        handle = 'h' + str(identity(module_id, label)).replace('-', 'g')
        texts.append((handle, '1', value))
        return handle + ';1'
    def emit(name, kind, fields, parent=None):
        groups.setdefault(kind, []).append(stat_record(name, kind, fields, parent))
    def effect_text(effect, fields, *, passive=False, default_name='自定义效果'):
        visible = bool(effect.display.name or effect.display.description)
        fields['DisplayName'] = text_handle(effect.id + ':name', effect.display.name or default_name)
        fields['Description'] = text_handle(effect.id + ':description', effect.display.description or '')
        if passive:
            properties = [v for v in fields.get('Properties', '').split(';') if v and v != 'IsHidden']
            if not visible:
                properties.append('IsHidden')
            fields['Properties'] = ';'.join(properties)
    dependency_manifests = {}
    def emit_family(effect, source_id, changes):
        records = resources['records']
        family = closure(source_id, records, isinstance(effect, GrantedSpell))
        mapping = {source_id: ids[effect.id]}
        for ref in family:
            if ref == source_id:
                continue
            upcast = re.fullmatch(r'(.+)(_[2-6])', ref)
            if upcast and upcast[1] in mapping:
                mapping[ref] = mapping[upcast[1]] + upcast[2]
            else:
                prefix = records[ref]['effective'].get('SpellType', '')
                mapping[ref] = (prefix + '_' if prefix else '') + 'MS_' + identity(module_id, effect.id + ':dependency:' + ref).hex
        for ref in family:
            record = records[ref]
            data = dict(record['effective'])
            if ref == source_id:
                data.update(changes)
            elif isinstance(effect, GrantedSpell) and re.fullmatch(re.escape(source_id) + r'_[2-6]', ref):
                data.update(spell_fields(effect, ref, records))
                data['DisplayName'] = changes['DisplayName']
            elif isinstance(effect, GrantedSpell) and record['type'] == 'SpellData':
                # Linked triggered spells keep their own costs/target form. Only compatible
                # effect magnitudes and radius propagate; no silent loss of delayed effects.
                profile = spell_profile(ref, records)
                linked = effect.model_copy(deep=True)
                linked.action_cost = linked.cooldown = linked.spell_slot = linked.range_m = None
                linked.remove_spell_slot = False
                if data.get('SpellContainerID') in mapping:
                    linked.action_cost, linked.cooldown = effect.action_cost, effect.cooldown
                    linked.spell_slot, linked.remove_spell_slot = effect.spell_slot, effect.remove_spell_slot
                if profile['range_field']:
                    linked.range_m = effect.range_m
                if linked.status_duration_turns is not None:
                    try:
                        status_duration(data.get('SpellProperties',''), linked.status_duration_turns)
                    except ValueError:
                        linked.status_duration_turns = None
                if not profile['area_field']:
                    linked.area_radius_m = None
                for parameter in ('damage', 'healing'):
                    if parameter not in profile['amount_fields']:
                        setattr(linked, parameter, None)
                data.update(spell_fields(linked, ref, records))
                data['DisplayName'] = text_handle(effect.id + ':' + ref + ':name', (effect.display.name or '独立技能') + '关联效果')
                data['Description'] = text_handle(effect.id + ':' + ref + ':description', '关联原生效果：' + ';'.join(data.get(k, '') for k in ('SpellProperties','SpellSuccess','AreaRadius')))
            # Every copied node describes its own final values, including its own
            # upcast cost. Never reuse stale native interpolation parameters.
            if ref != source_id:
                if record['type'] == 'SpellData':
                    labels = {'SpellProperties':'效果', 'SpellSuccess':'命中效果',
                              'TargetRadius':'距离（米）', 'AreaRadius':'区域（米）',
                              'UseCosts':'消耗', 'Cooldown':'冷却'}
                    description = '；'.join(label + '：' + data[k] for k, label in labels.items() if data.get(k))
                elif record['type'] == 'StatusData':
                    description = '关联状态。'
                    if data.get('Boosts'):
                        description += '状态效果：' + data['Boosts'] + '。'
                    for field, label in (('OnApplyFunctors','施加时'),('OnTickFunctors','每回合'),('OnRemoveFunctors','结束时')):
                        if data.get(field):
                            description += label + '执行关联原生效果。'
                else:
                    description = '关联被动：' + ';'.join(data.get(k, '') for k in ('Boosts','Conditions','StatsFunctors'))
                data['Description'] = text_handle(effect.id + ':' + ref + ':final-description', description)
            data['DescriptionParams'] = ''
            data = {k: rewrite_refs(v, mapping) for k, v in data.items()}
            if record['type'] == 'StatusData':
                data['StackId'] = mapping[ref]
            emit(mapping[ref], record['type'], data)
        dependency_manifests[effect.id] = mapping
    passives = [v for v in original.get('PassivesOnEquip', '').split(';') if v and v not in plan.removed_original_passives]
    for e in plan.effects:
        fields = {}
        summary = ''
        if isinstance(e, (ConstantEffect, NativeBonus, WeaponDamageBonus)):
            fields['Boosts'] = bonus_expression(e)
            summary = '装备时生效：' + fields['Boosts']
            kind = 'PassiveData'
        elif isinstance(e, PassiveCopy):
            source = resources['records'][e.base_passive]['effective']
            fields = dict(source)
            summary = '原生被动副本：' + e.base_passive + '；' + ';'.join(source.get(k, '') for k in ('Boosts', 'Conditions', 'StatsFunctors'))
            kind = 'PassiveData'
            effect_text(e, fields, passive=True, default_name='独立被动')
            emit_family(e, e.base_passive, fields)
            passives.append(ids[e.id])
            continue
        elif isinstance(e, IndependentStatus):
            source = resources['records'][e.base_status]['effective']
            fields = {k: v for k, v in source.items() if k in ('Icon', 'SoundLoop', 'SoundStop', 'StatusEffect')}
            ability_boost=[f'Ability({e.ability},{e.amount})'] if e.amount else []
            fields.update(StatusType='BOOST', StackId=ids[e.id], StackType={'replace': 'Overwrite', 'ignore': 'Ignore', 'additive': 'Additive'}[e.stacking], Boosts=';'.join(ability_boost + [bonus_expression(b) for b in e.bonuses]))
            summary = f'{fields["Boosts"]}；持续 {e.duration_turns} 回合；重复施加：{e.stacking}。'
            kind = 'StatusData'
        elif isinstance(e, TriggerEffect):
            fields['StatsFunctorContext'] = {'on_hit':'OnAttack', 'on_heal':'OnHeal', 'on_damaged':'OnDamaged'}[e.event]
            fields['Conditions'] = 'AttackedWithPassiveSourceWeapon() and IsAttack() and not IsMiss()' if e.event == 'on_hit' else ''
            if e.condition == 'target_full_health':
                fields['Conditions'] += ' and HasMaxHP()'
            target = 'SELF,' if e.target == 'self' else ''
            if e.action == 'status':
                ref = ids[e.status_draft_id] if e.status_draft_id else e.status_ref
                action = f'ApplyStatus({target}{ref},100,{e.duration_turns})'
            elif e.action == 'damage':
                action = f'DealDamage({e.dice},{e.damage_type},Magical)'
            else:
                action = f'RegainHitPoints({target}{e.dice})'
            fields['StatsFunctors'] = action
            summary = f'事件 {e.event}；条件 {e.condition}；对象 {e.target}：{action}'
            kind = 'PassiveData'
        else:
            source = resources['records'][e.base_spell]['effective']
            fields = spell_fields(e, e.base_spell, resources['records'])
            summary = '装备授予独立技能：' + e.base_spell + '；' + json.dumps({k: fields.get(k, source.get(k, '')) for k in ('SpellProperties', 'SpellSuccess', 'TargetRadius', 'AreaRadius', 'UseCosts', 'Cooldown')}, ensure_ascii=False)
            effect_text(e, fields, default_name='自定义技能')
            emit_family(e, e.base_spell, fields)
            passive_id = 'MS_' + identity(module_id, e.id + ':grant').hex
            emit(passive_id, 'PassiveData', {'Boosts': f'UnlockSpell({ids[e.id]})', 'DisplayName': fields['DisplayName'], 'Description': fields['Description'],
                'Properties': '' if e.display.name or e.display.description else 'IsHidden'})
            passives.append(passive_id)
            continue
        effect_text(e, fields, passive=kind == 'PassiveData')
        emit(ids[e.id], kind, fields)
        if kind == 'PassiveData':
            passives.append(ids[e.id])
    fields = {FIELD_MAP[k]: number(v) if isinstance(v, (int, float)) else v for k, v in plan.parameters.model_dump(exclude_none=True).items() if k in FIELD_MAP}
    if plan.effects or plan.removed_original_passives:
        fields['PassivesOnEquip'] = ';'.join(passives)
    default_boosts = original.get('DefaultBoosts', '')
    if plan.base_equipment == FIRST_BLOOD and OLD_PASSIVE in plan.removed_original_passives:
        # Normal and Honour differ; explicitly replace BOTH paths with the normal baseline.
        fields['DefaultBoosts'] = default_boosts
    if plan.parameters.enchantment is not None:
        default_boosts = re.sub(r'(?:^|;)WeaponEnchantment\(\d+\)', '', default_boosts).strip(';')
        fields['DefaultBoosts'] = ';'.join(filter(None, [default_boosts, f'WeaponEnchantment({plan.parameters.enchantment})']))
    if plan.parameters.weapon_properties is not None:
        fields['Weapon Properties'] = ';'.join(plan.parameters.weapon_properties)
    if plan.parameters.dexterity_rule:
        fields['Armor Class Ability'] = 'None' if plan.parameters.dexterity_rule == 'none' else 'Dexterity'
        fields['Ability Modifier Cap'] = '2' if plan.parameters.dexterity_rule == 'capped_2' else ''
    if new:
        fields['RootTemplate'] = root_id
    if fields or new:
        emit(equipment_id, base['type'], fields, base_name)
    if new or plan.display.model_dump(exclude_none=True) or plan.icon:
        root = ET.Element('save')
        ET.SubElement(root, 'version', major='4', minor='0', revision='9', build='331')
        region = ET.SubElement(root, 'region', id='Templates')
        children = ET.SubElement(ET.SubElement(region, 'node', id='Templates'), 'children')
        node = ET.SubElement(children, 'node', id='GameObjects')
        if not new:
            # A template override is a full node, not a Stats-style sparse overlay.
            for source in set(template['direct_field_sources'].values()):
                for candidate in ET.parse(ROOT / source).findall('.//node[@id="GameObjects"]'):
                    attr = candidate.find('./attribute[@id="MapKey"]')
                    if attr is not None and attr.get('value') == key:
                        children.remove(node)
                        node = deepcopy(candidate)
                        children.append(node)
        attrs = {'MapKey': ('FixedString', root_id), 'Type': ('FixedString', 'item')}
        if new:
            visual_parent = plan.appearance_equipment.removeprefix('equipment:') if plan.appearance_equipment else key
            attrs.update(ParentTemplateId=('FixedString', visual_parent), Name=('LSString', equipment_id), Stats=('FixedString', equipment_id))
        if plan.icon:
            attrs['Icon'] = ('FixedString', plan.icon)
        if plan.appearance_equipment:
            visual = resources['templates'][plan.appearance_equipment.removeprefix('equipment:')]['effective']
            for field in ('VisualTemplate', 'PhysicsTemplate', 'EquipmentTypeID'):
                if field in visual:
                    attrs[field] = (visual[field]['type'], visual[field]['value'])
        for field, (kind, value) in attrs.items():
            old = node.find(f'./attribute[@id="{field}"]')
            if old is not None:
                node.remove(old)
            ET.SubElement(node, 'attribute', id=field, type=kind, value=value)
        for field, value in (('DisplayName', plan.display.name), ('Description', plan.display.description)):
            if value is not None or new:
                old = node.find(f'./attribute[@id="{field}"]')
                if old is not None:
                    node.remove(old)
                handle = text_handle('equipment:' + field, value or '独立制作装备；效果见词条说明。').split(';')[0]
                ET.SubElement(node, 'attribute', id=field, type='TranslatedString', handle=handle, version='1')
        files[Path('Public') / module / 'RootTemplates/_merged.lsx'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    if new:
        files[Path('Public') / module / 'OneTimeRewards/OneTimeRewards.lsx'] = rewards_xml(module_id, root_id)
    for kind, contents in groups.items():
        files[Path('Public') / module / 'Stats/Generated/Data' / (kind + '.txt')] = ''.join(contents).encode()
    if texts:
        files[Path('Mods') / module / 'Localization/Chinese/chinese.xml'] = localization(texts)
    tree = ET.parse(ROOT / 'templates/module.lsx')
    info = tree.find('.//node[@id="ModuleInfo"]')
    for a in info.findall('attribute'):
        if a.get('id') in ('UUID', 'Folder', 'Name', 'Description'):
            a.set('value', {'UUID': module_id, 'Folder': module, 'Name': plan.display.name or 'ModSuperman 1.1', 'Description': plan.user_goal}[a.get('id')])
    for child in info.findall('children'):
        info.remove(child)
    files[Path('Mods') / module / 'meta.lsx'] = ET.tostring(tree.getroot(), encoding='utf-8', xml_declaration=True)
    manifest = {'module_uuid': module_id, 'plan_digest': digest(plan), 'equipment': equipment_id, 'root_template': root_id, 'effect_ids': ids, 'native_dependency_copies': dependency_manifests, 'template_audit': resources.get('body_template_audit', {}).get('templates', {}).get(plan.appearance_equipment.removeprefix('equipment:') if plan.appearance_equipment else key), 'mode': plan.mode, 'base_record': base_name, 'changed_fields': fields, 'game_validation': 'not_performed', 'warnings': ['Shared Stats overrides affect all instances and inheriting records.', 'New equipment uses a stable one-time camp chest reward without chapter conditions.', 'Existing-save delivery and actual game behavior are not verified.']}
    return files, manifest


def check_files(files, manifest, resources):
    """Independent structural/reference checks on compiler output before conversion."""
    from scripts.equipment_catalog import parse_stats
    entries = {}
    text_handles = set()
    native_text_handles = {v.split(';')[0] for r in resources['records'].values()
                           for k,v in r['effective'].items() if k in ('DisplayName','Description')}
    for path, content in files.items():
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Invalid output path')
        if path.suffix == '.xml':
            for entry in ET.fromstring(content).findall('content'):
                handle = entry.get('contentuid')
                if handle in text_handles:
                    raise ValueError('Duplicate localization handle')
                text_handles.add(handle)
        if path.parent.name == 'Data' and path.suffix == '.txt':
            for entry in parse_stats(content.decode(), str(path)):
                if entry.name in entries:
                    raise ValueError('Duplicate generated Stats ID')
                if entry.name in resources['records'] and entry.name != manifest['equipment']:
                    raise ValueError('Unexpected public record override')
                entries[entry.name] = entry
    if manifest['mode'] == 'create_new' and manifest['equipment'] in resources['records']:
        raise ValueError('New equipment collides with original')
    for entry in entries.values():
        if entry.parent and entry.parent not in resources['records']:
            raise ValueError('Unknown inheritance target')
        for field in ('DisplayName', 'Description'):
            if entry.fields.get(field) and entry.fields[field].split(';')[0] not in text_handles | native_text_handles:
                raise ValueError('Missing localized text')
        for ref in filter(None, entry.fields.get('PassivesOnEquip', '').split(';')):
            kind = entries[ref].kind if ref in entries else resources['records'].get(ref, {}).get('type')
            if kind != 'PassiveData':
                raise ValueError('Dangling passive reference')
        for ref in re.findall(r'UnlockSpell\(([^,)]+)', entry.fields.get('Boosts', '')):
            if (entries[ref].kind if ref in entries else resources['records'].get(ref, {}).get('type')) != 'SpellData':
                raise ValueError('Dangling generated spell')
    from scripts.native_dependencies_v11 import dependencies
    combined = dict(resources['records'])
    combined.update({k:{'type':v.kind, 'effective':v.fields} for k,v in entries.items()})
    for mapping in manifest.get('native_dependency_copies', {}).values():
        for copied in mapping.values():
            dependencies(copied, combined)
    if manifest['mode'] == 'create_new':
        equip = entries[manifest['equipment']]
        if equip.fields.get('RootTemplate') != manifest['root_template']:
            raise ValueError('Equipment/template mismatch')
        rootfiles = [v for p, v in files.items() if p.name == '_merged.lsx']
        root = ET.fromstring(rootfiles[0])
        if root.find('.//attribute[@id="Stats"]').get('value') != manifest['equipment']:
            raise ValueError('Template/Stats mismatch')
        reward_files = [v for p,v in files.items() if p.name == 'OneTimeRewards.lsx']
        if len(reward_files)!=1:raise ValueError('Missing camp chest reward')
        check_rewards(reward_files[0],manifest['module_uuid'],manifest['root_template'])


def generate_draft(draft, module_id, output_root, *, catalog, resources, packager=DIVINE):
    """Confirmed draft -> source -> format conversion -> PAK -> unpack equivalence."""
    module_id = str(uuid.UUID(str(module_id)))
    plan = draft.begin_generation(catalog, resources)
    directory = None
    result = {'source_generation': 'pending', 'conversion': 'pending', 'pak_creation': 'pending', 'package_check': 'pending', 'game_validation': 'not_performed'}
    try:
        files, manifest = render_plan(plan, module_id, catalog=catalog, resources=resources,
                                      text_receipt=draft.text_receipt)
        check_files(files, manifest, resources)
        parent = Path(output_root) / str(uuid.UUID(str(module_id))) / digest(plan)[:16]
        parent.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix='attempt-', dir=parent))
        source = directory / 'mod-source'
        for relative, data in files.items():
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        result.update(manifest, source_generation='passed')
        for path in list(source.rglob('*.xml')):
            # Mods/<module>/Localization/<language> is the documented XML loader
            # location. Binary round-trip is a check, not a replacement at this path.
            compiled_loca = directory / 'localization-check.loca'
            run_tool(packager, '-a', 'convert-loca', '-s', str(path), '-d', str(compiled_loca))
            roundtrip = directory / 'localization-roundtrip.xml'
            run_tool(packager, '-a', 'convert-loca', '-s', str(compiled_loca), '-d', str(roundtrip))
            def contents(p):
                return sorted((e.get('contentuid'), e.get('version'), e.text) for e in ET.parse(p).findall('content'))
            if contents(path) != contents(roundtrip):
                raise ValueError('Localization round-trip changed text')
        for path in list(source.rglob('*.lsx')):
            if path.name == 'OneTimeRewards.lsx':
                binary = directory / 'rewards-check.lsf'
                roundtrip = directory / 'rewards-roundtrip.lsx'
                run_tool(packager, '-a', 'convert-resource', '-s', str(path), '-d', str(binary), '-i', 'lsx', '-o', 'lsf')
                run_tool(packager, '-a', 'convert-resource', '-s', str(binary), '-d', str(roundtrip), '-i', 'lsf', '-o', 'lsx')
                check_rewards(roundtrip.read_bytes(), module_id, manifest['root_template'], binary_roundtrip=True)
            if path.name == '_merged.lsx':
                run_tool(packager, '-a', 'convert-resource', '-s', str(path), '-d', str(path.with_suffix('.lsf')), '-i', 'lsx', '-o', 'lsf')
                # Round-trip proves the resource can be parsed, beyond opaque package copying.
                run_tool(packager, '-a', 'convert-resource', '-s', str(path.with_suffix('.lsf')), '-d', str(directory / 'template-roundtrip.lsx'), '-i', 'lsf', '-o', 'lsx')
                original_attrs = [(a.get('id'), a.get('value'), a.get('handle')) for a in ET.parse(path).findall('.//attribute')]
                actual_attrs = [(a.get('id'), a.get('value'), a.get('handle')) for a in ET.parse(directory / 'template-roundtrip.lsx').findall('.//attribute')]
                if sorted(original_attrs) != sorted(actual_attrs):
                    raise ValueError('Template round-trip changed attributes')
                path.unlink()
        result['conversion'] = 'passed'
        expected = {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()}
        pak = directory / ('ModSuperman_' + str(module_id) + '.pak')
        run_tool(packager, '-a', 'create-package', '-s', str(source), '-d', str(pak))
        if not pak.is_file() or not pak.stat().st_size:
            raise ValueError('Missing package')
        result['pak_creation'] = 'passed'
        unpacked = directory / 'unpacked'
        run_tool(packager, '-a', 'extract-package', '-s', str(pak), '-d', str(unpacked))
        if expected != {p.relative_to(unpacked): p.read_bytes() for p in unpacked.rglob('*') if p.is_file()}:
            raise ValueError('Package contents mismatch')
        result.update(package_check='passed', pak_sha256=hashlib.sha256(pak.read_bytes()).hexdigest())
        notes = ['Mod-Superman 1.1 本地程序验收产物',
                 r"退出游戏后，将 PAK 文件直接放入 %LOCALAPPDATA%\Larian Studios\Baldur's Gate 3\Mods（可在资源管理器地址栏输入该路径）。",
                 '不要放入 Steam 游戏安装目录的 Data/Mods，也不要把整个 ZIP 放入 Mods。',
                 '重新启动游戏，在主菜单的 Mod 管理器已安装列表中查找 ModSuperman 1.1 并启用；本工具不自动安装。',
                 '当前产物已做格式转换、打包和解包检查；游戏内效果未测试。',
                 '不要同时启用修改相同 Stats 或 TreasureTable 的测试包。',
                 '卸载：停用本包，重启游戏并加载启用前的备份存档。',
                 '模式：' + plan.mode, '方案摘要：' + digest(plan)]
        if plan.mode == 'create_new':
            notes.extend(['获取入口：营地个人宝箱；启用 Mod 并加载存档后返回营地查看。',
                          '不限制章节、不依赖商人。按同一奖励标识一次性发放，不随读档重复补发。',
                          '各章节、已有存档和多人情况下的实际发放尚未游戏验证。'])
            for behavior in manifest.get('template_audit', {}).get('special_actions', []):
                notes.append('已确认保留的特殊行为：' + behavior.get('description', behavior.get('name', behavior['kind'])))
        (directory / '使用说明.txt').write_text('\n'.join(notes), encoding='utf-8')
        draft.finish(success=True)
        return pak
    except Exception as exc:
        result['error'] = str(exc)
        draft.finish(success=False, failure_reason=str(exc))
        raise
    finally:
        if directory is not None and directory.exists():
            (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    import argparse
    from backend.crafting_v11 import Draft
    from scripts.equipment_catalog import load_catalog
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--module-id', help='Reuse the same UUID when retrying this production plan')
    parser.add_argument('--confirm-digest', help='Exact plan digest from preview; omitted means preview only')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/v1.1/phase-b')
    args = parser.parse_args()
    plan = Plan.model_validate_json(args.plan.read_text(encoding='utf-8-sig'))
    catalog, resources = load_catalog(), load_resources()
    draft = Draft(plan)
    issues = draft.review(catalog, resources)
    preview = {'revision': 1, 'digest': digest(plan), 'module_id': args.module_id or str(uuid.uuid4()), 'issues': issues, 'plan': plan.model_dump(mode='json'), 'game_validation': 'not_performed'}
    audit = resources.get('body_template_audit', {}).get('templates', {}).get((plan.appearance_equipment or plan.base_equipment).removeprefix('equipment:'), {})
    preview['template_behavior_details'] = audit.get('special_actions', [])
    preview['body_profiles'] = list(v['name'] for v in audit.get('body_mapping', {}).values())
    if not args.confirm_digest:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return
    if not args.module_id:
        parser.error('--module-id from preview is required for generation and retry')
    draft.confirm(expected_revision=1, expected_digest=args.confirm_digest)
    print(generate_draft(draft, args.module_id, args.output, catalog=catalog, resources=resources))


if __name__ == '__main__':
    main()
