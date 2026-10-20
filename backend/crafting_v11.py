"""V1.1 draft contract and confirmation gate. Phase B compiler connected; v1 HTTP unchanged."""
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator, field_validator
from backend.ai_protocol import StrictModel
from scripts.generate_equipment import validate_request

Identifier = Annotated[str, Field(min_length=1, max_length=150, pattern=r'^[A-Za-z0-9_:-]+$')]
Text = Annotated[str, Field(min_length=1, max_length=2000)]


class Display(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=60)] | None = None
    description: Text | None = None

    @field_validator('name', 'description')
    @classmethod
    def plain_text(cls, value):
        if value is not None and (not value.strip() or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE, 0xFFFF) for c in value)):
            raise ValueError('Display text must be nonblank without control characters')
        return value


class BaseParameters(StrictModel):
    weapon_properties: list[Literal['Finesse', 'Light', 'Heavy', 'Reach', 'Twohanded', 'Versatile', 'Thrown', 'Melee', 'Ranged', 'Dippable', 'Magical']] | None = None
    dexterity_rule: Literal['none', 'full', 'capped_2'] | None = None
    damage: Annotated[str, Field(pattern=r'^(?:[1-9]|10)d(?:4|6|8|10|12|20)$')] | None = None
    versatile_damage: Annotated[str, Field(pattern=r'^(?:[1-9]|10)d(?:4|6|8|10|12|20)$')] | None = None
    weight_kg: Annotated[float, Field(ge=0, le=100)] | None = None
    rarity: Literal['Common', 'Uncommon', 'Rare', 'VeryRare', 'Legendary'] | None = None
    armor_class: Annotated[int, Field(ge=0, le=30)] | None = None
    enchantment: Annotated[int, Field(ge=0, le=5)] | None = None
    value: Annotated[int, Field(ge=0, le=100000)] | None = None
    damage_type: Literal['Slashing', 'Piercing', 'Bludgeoning', 'Acid', 'Cold', 'Fire', 'Force',
                         'Lightning', 'Necrotic', 'Poison', 'Psychic', 'Radiant', 'Thunder'] | None = None


class ConstantEffect(StrictModel):
    kind: Literal['constant']
    id: Identifier
    ability: Literal['Strength', 'Dexterity', 'Constitution', 'Intelligence', 'Wisdom', 'Charisma']
    amount: Annotated[int, Field(ge=-10, le=10)]
    display: Display = Field(default_factory=Display)


class WeaponDamageBonus(StrictModel):
    """Equipped passive affecting the wearer's weapons, not the source item."""
    kind: Literal['weapon_damage']
    id: Identifier
    dice: Annotated[str, Field(pattern=r'^(?:[1-9]|10)d(?:4|6|8|10|12|20)$')]
    damage_type: Literal['Slashing', 'Piercing', 'Bludgeoning', 'Acid', 'Cold', 'Fire', 'Force',
                         'Lightning', 'Necrotic', 'Poison', 'Psychic', 'Radiant', 'Thunder']
    display: Display = Field(default_factory=Display)


class TriggerEffect(StrictModel):
    kind: Literal['trigger']
    id: Identifier
    event: Literal['on_hit', 'on_heal', 'on_damaged']
    condition: Literal['always', 'target_full_health']
    target: Literal['self', 'target']
    action: Literal['status', 'damage', 'heal'] = 'status'
    dice: Annotated[str, Field(pattern=r'^(?:[1-9]|10)d(?:4|6|8|10|12|20)$')] | None = None
    damage_type: Literal['Slashing', 'Piercing', 'Bludgeoning', 'Acid', 'Cold', 'Fire', 'Force', 'Lightning', 'Necrotic', 'Poison', 'Psychic', 'Radiant', 'Thunder'] | None = None
    status_ref: Identifier | None = None
    status_draft_id: Identifier | None = None
    duration_turns: Annotated[int, Field(ge=1, le=10)]
    display: Display = Field(default_factory=Display)

    @model_validator(mode='after')
    def one_status(self):
        if self.action != 'status':
            if self.status_ref or self.status_draft_id or not self.dice:
                raise ValueError('Damage/heal requires dice and no status reference')
            if (self.action == 'damage') != (self.damage_type is not None):
                raise ValueError('Damage type is required only for damage')
            return self
        if self.dice or self.damage_type or (self.status_ref is None) == (self.status_draft_id is None):
            raise ValueError('Choose exactly one native or draft status reference')
        return self


class SpellSlotCost(StrictModel):
    level: Annotated[int, Field(ge=1, le=6)]
    amount: Annotated[int, Field(ge=1, le=3)] = 1


class GrantedSpell(StrictModel):
    kind: Literal['grant_spell']
    id: Identifier
    # Catalog reference, not an AI-assigned output identifier.
    base_spell: Identifier
    display: Display = Field(default_factory=Display)
    range_m: Annotated[float, Field(gt=0, le=100)] | None = None
    area_radius_m: Annotated[float, Field(gt=0, le=100)] | None = None
    action_cost: Literal['action', 'bonus_action', 'none'] | None = None
    cooldown: Literal['once_per_turn', 'short_rest', 'long_rest', 'none'] | None = None
    spell_slot: SpellSlotCost | None = None
    remove_spell_slot: bool = False
    healing: Annotated[str, Field(pattern=r'^(?:[1-9]|10)d(?:4|6|8|10|12|20)$')] | None = None
    damage: Annotated[str, Field(pattern=r'^(?:[1-9]|10)d(?:4|6|8|10|12|20)$')] | None = None
    status_duration_turns: Annotated[int, Field(ge=1, le=10)] | None = None


class NativeBonus(StrictModel):
    kind: Literal['bonus']
    id: Identifier
    bonus: Literal['initiative', 'movement', 'skill', 'saving_throw', 'armor_class', 'resistance']
    amount: Annotated[int, Field(ge=-10, le=10)] = 1
    selector: Identifier | None = None
    display: Display = Field(default_factory=Display)


class IndependentStatus(StrictModel):
    kind: Literal['independent_status']
    id: Identifier
    base_status: Identifier
    display: Display
    duration_turns: Annotated[int, Field(ge=1, le=10)]
    stacking: Literal['replace', 'ignore', 'additive']
    ability: Literal['Strength', 'Dexterity', 'Constitution', 'Intelligence', 'Wisdom', 'Charisma']
    bonuses: list[NativeBonus] = Field(default_factory=list, max_length=12)
    amount: Annotated[int, Field(ge=-10, le=10)]


class PassiveCopy(StrictModel):
    kind: Literal['passive_copy']
    id: Identifier
    base_passive: Identifier
    display: Display = Field(default_factory=Display)


Effect = Annotated[ConstantEffect | NativeBonus | WeaponDamageBonus | PassiveCopy | TriggerEffect | GrantedSpell | IndependentStatus, Field(discriminator='kind')]


class Plan(StrictModel):
    schema_version: Literal['1.1-draft-4'] = '1.1-draft-4'
    mode: Literal['modify_existing', 'create_new']
    base_equipment: Identifier
    user_goal: Text
    display: Display = Field(default_factory=Display)
    parameters: BaseParameters = Field(default_factory=BaseParameters)
    effects: list[Effect] = Field(default_factory=list, max_length=30)
    removed_original_passives: list[Identifier] = Field(default_factory=list, max_length=30)
    acquisition: Identifier | None = None
    appearance_equipment: Identifier | None = None
    template_behavior: Literal['reject_special', 'preserve_reviewed'] = 'reject_special'
    icon: Identifier | None = None
    unresolved: list[Text] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def consistency(self):
        if self.mode == 'create_new' and self.acquisition in (None, 'dammon_act1'):
            self.acquisition = 'camp_chest'
        ids = [effect.id for effect in self.effects]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate draft effect ID')
        if len(self.removed_original_passives) != len(set(self.removed_original_passives)):
            raise ValueError('Duplicate removed passive')
        if self.mode == 'modify_existing' and self.acquisition is not None:
            raise ValueError('Existing equipment retains acquisition')
        local_statuses = {e.id for e in self.effects if isinstance(e, IndependentStatus)}
        used_statuses = set()
        for effect in self.effects:
            if isinstance(effect, TriggerEffect) and effect.status_draft_id:
                if effect.status_draft_id not in local_statuses:
                    raise ValueError('Missing or wrong-type draft status reference')
                used_statuses.add(effect.status_draft_id)
                status = next(e for e in self.effects if e.id == effect.status_draft_id)
                if status.duration_turns != effect.duration_turns:
                    raise ValueError('Status and trigger durations disagree')
        if local_statuses - used_statuses:
            raise ValueError('Independent status must be used by a trigger')
        return self


def digest(plan):
    return hashlib.sha256(json.dumps(plan.model_dump(mode='json'), ensure_ascii=False,
                                     sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check_capabilities(plan, equipment_catalog, resources=None, text_receipt=None):
    """One gate for both AI/manual callers; discovery never enables generation."""
    if resources is not None:
        from scripts.crafting_compiler_v11 import validate_plan
        return validate_plan(plan, equipment_catalog, resources, text_receipt=text_receipt)
    issues = []
    if plan.unresolved:
        issues.append('unresolved_questions')
    if plan.mode == 'create_new':
        issues.append('create_generator_and_acquisition_not_implemented')
    if plan.effects:
        issues.append('native_effect_compiler_not_implemented')
    if resources is None and (plan.effects or plan.mode == 'create_new' or plan.removed_original_passives):
        issues.append('resource_catalog_required')
    if resources is not None:
        issues.extend(check_resource_links(plan, resources))
    if plan.removed_original_passives:
        issues.append('original_effect_removal_not_implemented')
    if plan.display.description is not None:
        issues.append('description_localization_not_implemented')
    changes = plan.parameters.model_dump(exclude_none=True)
    for field in list(changes):
        if field not in ('damage', 'versatile_damage', 'weight_kg', 'rarity'):
            issues.append(f'parameter_not_implemented:{field}')
            changes.pop(field)
    if plan.display.name is not None:
        changes['name'] = plan.display.name
    if plan.base_equipment not in equipment_catalog['items']:
        issues.append('unknown_base_equipment')
    elif changes:
        try:
            validate_request({'object': plan.base_equipment, 'changes': changes},
                             catalog=equipment_catalog, allow_unverified=True)
        except ValueError as error:
            issues.append(str(error))
    elif not plan.effects and not plan.removed_original_passives:
        issues.append('empty_changes')
    return issues


def check_resource_links(plan, resources):
    """Validate references independently of compiler availability; path-specific errors."""
    issues = []
    records = resources['records']
    key = plan.base_equipment.removeprefix('equipment:')
    template = resources['templates'].get(key)
    if template is None:
        return ['base_equipment:missing_template']
    base = records[template['stats']]
    if plan.mode == 'create_new':
        current_audit = resources.get('body_template_audit', {}).get('templates', {}).get(key)
        qualified = (current_audit['qualified'] if current_audit is not None
                     else template['create_eligibility']['status'] == 'base_template_qualified')
        if not qualified:
            issues.append('base_equipment:unqualified_visual')
        if plan.acquisition != 'camp_chest':
            issues.append('acquisition:unknown_or_unverified')
    for field in ('damage', 'versatile_damage', 'damage_type', 'enchantment'):
        if getattr(plan.parameters, field) is not None and base['type'] != 'Weapon':
            issues.append(f'parameters.{field}:requires_weapon')
    if plan.parameters.armor_class is not None and base['type'] != 'Armor':
        issues.append('parameters.armor_class:requires_armor')
    existing = set(base['effective'].get('PassivesOnEquip', '').split(';'))
    for ref in plan.removed_original_passives:
        if ref not in existing:
            issues.append(f'removed_original_passives.{ref}:not_on_base')
    for effect in plan.effects:
        ref, kind = None, None
        if isinstance(effect, GrantedSpell):
            ref, kind = effect.base_spell, 'SpellData'
        elif isinstance(effect, IndependentStatus):
            ref, kind = effect.base_status, 'StatusData'
        elif isinstance(effect, TriggerEffect) and effect.status_ref:
            ref, kind = effect.status_ref, 'StatusData'
        if ref and (ref not in records or records[ref]['type'] != kind):
            issues.append(f'effects.{effect.id}:missing_or_wrong_type:{ref}')
        elif ref:
            if any(a['status'] != 'checked' for a in records[ref].get('expression_reference_check', {}).values()):
                issues.append(f'effects.{effect.id}:unreviewed_expression_dependency')
    return issues


class Draft:
    """Server-owned state. Callers receive copies, preventing silent mutation."""
    def __init__(self, plan):
        self._plan = Plan.model_validate(plan.model_dump())
        self.revision = 1
        self.state = 'draft'
        self.confirmation = None
        self.history = []
        self.failure_reason = None
        self.text_receipt = None

    @property
    def plan(self):
        return self._plan.model_copy(deep=True)

    def replace(self, plan, *, source: Literal['manual', 'ai'], expected_revision):
        if source not in ('manual', 'ai') or type(expected_revision) is not int or expected_revision != self.revision:
            raise ValueError('Invalid source or stale revision')
        if self.state == 'generating':
            raise ValueError('Cannot edit a running generation')
        new = Plan.model_validate(plan.model_dump())
        old = digest(self._plan)
        self._plan = new
        self.revision += 1
        self.confirmation = None
        self.state = 'draft'
        self.text_receipt = None
        self.failure_reason = None
        self.history.append({'revision': self.revision, 'source': source, 'before': old, 'after': digest(new),
                             'plan': new.model_dump(mode='json')})

    def review(self, catalog, resources=None, text_receipt=None):
        if self.state in ('generating', 'succeeded'):
            raise ValueError('Edit completed plan before review')
        issues = check_capabilities(self._plan, catalog, resources, text_receipt)
        self.text_receipt = text_receipt
        self._reviewed_catalog_digest = hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
        self._reviewed_resources_digest = resource_digest(resources)
        self.confirmation = None
        self.state = ('needs_clarification' if self._plan.unresolved else 'unsupported') if issues else 'ready'
        return issues

    def confirm(self, *, expected_revision, expected_digest):
        if self.state != 'ready' or type(expected_revision) is not int or expected_revision != self.revision or expected_digest != digest(self._plan):
            raise ValueError('Plan is not ready or preview is stale')
        self.confirmation = (self.revision, digest(self._plan))
        self.state = 'confirmed'

    def begin_generation(self, catalog, resources=None):
        if (self.state != 'confirmed' or self.confirmation != (self.revision, digest(self._plan))
                or self._reviewed_catalog_digest != hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
                or self._reviewed_resources_digest != resource_digest(resources)
                or check_capabilities(self._plan, catalog, resources, self.text_receipt)):
            raise ValueError('Confirmation or capabilities invalid')
        self.state = 'generating'
        return self.plan

    def finish(self, *, success, failure_reason=None):
        if self.state != 'generating' or type(success) is not bool or (not success and not failure_reason):
            raise ValueError('Invalid generation completion')
        self.state = 'succeeded' if success else 'failed'
        self.failure_reason = None if success else failure_reason


def resource_digest(resources):
    return hashlib.sha256(json.dumps(resources, sort_keys=True).encode()).hexdigest() if resources is not None else None


def edit_effect(draft, *, action, effect_id, value=None, source, expected_revision):
    """Deleting a draft effect never implies removing a native passive."""
    payload = draft.plan.model_dump()
    effects = payload['effects']
    indices = [i for i, effect in enumerate(effects) if effect['id'] == effect_id]
    if action == 'add' and not indices and value and value.get('id') == effect_id:
        effects.append(value)
    elif action == 'update' and indices and value and value.get('id') == effect_id:
        effects[indices[0]] = value
    elif action == 'delete' and indices and value is None:
        effects.pop(indices[0])
    else:
        raise ValueError('Invalid effect operation')
    draft.replace(Plan.model_validate(payload), source=source, expected_revision=expected_revision)


def restore_parameter(draft, field, *, source, expected_revision):
    if field not in BaseParameters.model_fields:
        raise ValueError('Unknown base parameter')
    payload = draft.plan.model_dump()
    payload['parameters'][field] = None  # inheritance, not a guessed original value
    draft.replace(Plan.model_validate(payload), source=source, expected_revision=expected_revision)
