"""Native dependency rules: audited expressions, typed links, bounded acyclic copies."""
import re
from scripts.resource_audit_v11 import calls

EXPRESSION_FIELDS={'Boosts','DefaultBoosts','StatsFunctors','OnApplyFunctors','OnRemoveFunctors','TickFunctors','SpellProperties','SpellSuccess','SpellFail','Conditions','TargetConditions','CycleConditions','SpellRoll','OnApplyRoll','RemoveConditions','BoostConditions'}
EXPRESSION_FIELDS.update({'EnabledConditions','ToggleOffFunctors','ToggleOnFunctors','OnApplyConditions','AoEConditions','ExtraProjectileTargetConditions','ForkingConditions','RequirementConditions','OriginSpellFail','OriginSpellProperties','OriginSpellRoll','OriginSpellSuccess','OriginTargetConditions','ThrowableSpellProperties','ThrowableSpellRoll','ThrowableSpellSuccess','ThrowableTargetConditions'})
# Names verified in original records. Inputs are immutable game data, never user expressions.
FUNCTIONS=set('Ability Initiative ActionResource Skill RollBonus AC Resistance WeaponDamage WeaponEnchantment WeaponProperty StatusImmunity Advantage Disadvantage UnlockSpell ApplyStatus RemoveStatus HasStatus DealDamage RegainHitPoints IF Character Dead Self Enemy Ally Tagged Item IsAttack IsMiss AttackedWithPassiveSourceWeapon HasMaxHP HasMaxHPWithoutTemporaryHP IsDamageTypeFire IsDamageTypePiercing IsKillingBlow Attack SavingThrow LevelMapValue ClassLevel ProficiencyBonus ConditionResult IsMeleeAttack IsRangedAttack IsWeaponAttack HasPassive IsCritical Combat SurfaceChange CreateSurface RestoreResource RemoveCause UseSpell'.split())
# KingsKnife native passives: numeric boosts and context predicates only;
# none carries a Stats/Passive/Status/Spell identifier to clone or resolve.
FUNCTIONS.update({'ReduceCriticalAttackThreshold','AttackingWithMeleeWeapon','Reroll','HasObscuredState'})
REF_FUNCTIONS={'StatusImmunity':('StatusData',0),'UseSpell':('SpellData',0),'UnlockSpell':('SpellData',0),'ApplyStatus':('StatusData',0),'HasStatus':('StatusData',0),'RemoveStatus':('StatusData',0),'HasPassive':('PassiveData',0)}
LIST_FIELDS={'Passives':'PassiveData','PassivesOnEquip':'PassiveData','StatusOnEquip':'StatusData','ContainerSpells':'SpellData'}
SINGLE_FIELDS={'RootSpellID':'SpellData'}
SINGLE_FIELDS.update({'SpellContainerID':'SpellData','FollowUpOriginalSpell':'SpellData','ConcentrationSpellID':'SpellData','AiCalculationSpellOverride':'SpellData','CombatAIOverrideSpell':'SpellData','ItemWallStatus':'StatusData'})


def dependencies(name,records):
    record=records.get(name)
    if record is None:raise ValueError('missing_native_record:'+name)
    refs=set();fields=record['effective']
    for field,expression in fields.items():
        if field in ('AuraStatuses','InterruptPrototype') and expression:
            raise ValueError(name+':external_dependency_requires_profile:'+field)
        if field in EXPRESSION_FIELDS and expression.strip():
            parsed=calls(expression)
            if not parsed:raise ValueError(name+':unparsed:'+field)
            for function,args in parsed:
                if function not in FUNCTIONS:raise ValueError(name+':unreviewed_function:'+function)
                if function in REF_FUNCTIONS:
                    kind,index=REF_FUNCTIONS[function]
                    if function=='ApplyStatus' and args[0] in ('SELF','TARGET','OWNER'):index=1
                    if len(args)<=index:raise ValueError(name+':missing_argument:'+function)
                    ref=args[index].strip("'\"")
                    if records.get(ref,{}).get('type')!=kind:raise ValueError(name+':missing_or_wrong_type:'+ref)
                    # Predicates, immunity and removal address existing game state; cloning
                    # these targets would change semantics (e.g. immunity to SURPRISED).
                    if function not in ('HasStatus', 'HasPassive', 'StatusImmunity', 'RemoveStatus'):
                        refs.add(ref)
        elif field in LIST_FIELDS:
            for ref in filter(None,(s.strip() for s in expression.split(';'))):
                if records.get(ref,{}).get('type')!=LIST_FIELDS[field]:raise ValueError(name+':missing_or_wrong_type:'+ref)
                refs.add(ref)
        elif field in SINGLE_FIELDS and expression:
            if records.get(expression,{}).get('type')!=SINGLE_FIELDS[field]:raise ValueError(name+':missing_or_wrong_type:'+expression)
            if field not in ('RootSpellID','SpellContainerID'):
                refs.add(expression)
    return refs


def closure(name,records,include_upcasts=False):
    done=set();active=set();ordered=[]
    def visit(ref):
        if ref in active:raise ValueError('native_dependency_cycle:'+ref)
        if ref in done:return
        if len(done)+len(active)>100:raise ValueError('native_dependency_limit')
        active.add(ref)
        for dep in sorted(dependencies(ref,records)):visit(dep)
        active.remove(ref);done.add(ref);ordered.append(ref)
    visit(name)
    container=records[name]['effective'].get('SpellContainerID')
    if container:
        visit(container)
    if include_upcasts:
        # Include upcasts of linked/container spells as well as the selected root.
        scanned=set()
        while done-scanned:
            selected=sorted(done-scanned)
            scanned.update(selected)
            for base in selected:
                if records[base]['type']=='SpellData':
                    for level in range(2,7):
                        ref=base+'_'+str(level)
                        if ref in records and records[ref]['type']=='SpellData':visit(ref)
    return ordered


def rewrite_refs(value,mapping):
    # Only complete native IDs; never substrings, UUIDs or arbitrary model data.
    if not mapping:return value
    return re.sub(r'(?<![A-Za-z0-9_])('+ '|'.join(re.escape(k) for k in sorted(mapping,key=len,reverse=True))+r')(?![A-Za-z0-9_])',lambda m:mapping[m[0]],value)


def replace_amount(expression,function,new):
    """Replace one audited functor's amount, retaining target/type/other arguments."""
    starts=list(re.finditer(r'\b'+function+r'\(',expression))
    if len(starts)!=1:raise ValueError('ambiguous_effect_parameter:'+function)
    start=starts[0].end();depth=0;quote=None;end=None
    for i in range(start,len(expression)):
        c=expression[i]
        if quote:
            if c==quote:quote=None
        elif c in "'\"":quote=c
        elif c=='(':depth+=1
        elif c==')':
            if depth==0:end=i;break
            depth-=1
        elif c==',' and depth==0:end=i;break
    if end is None:raise ValueError('malformed_functor')
    if expression[start:end].strip() in ('SELF','TARGET','OWNER'):
        # targeted function amounts follow the target token
        tail=replace_amount(function+'('+expression[end+1:],function,new)
        return expression[:end+1]+tail[len(function)+1:]
    return expression[:start]+new+expression[end:]


def spell_profile(name,records):
    fields=records[name]['effective'];kind=fields.get('SpellType')
    if kind not in ('Target','Projectile','Shout'):raise ValueError('spell_type_requires_profile:'+str(kind))
    closure(name,records,True)
    amounts={}
    for function,label in [('RegainHitPoints','healing'),('DealDamage','damage')]:
        matches=[f for f in ('SpellProperties','SpellSuccess') if len(re.findall(r'\b'+function+r'\(',fields.get(f,'')))==1]
        if len(matches)==1:amounts[label]=matches[0]
    return {'type':kind,'amount_fields':amounts,'range_field':'TargetRadius' if kind!='Shout' else None,'area_field':'AreaRadius' if 'AreaRadius' in fields else None}
