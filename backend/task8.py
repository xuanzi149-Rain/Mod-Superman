"""Task8 in-memory workflow. No web routes, database migration or UI changes."""
import copy
import json
import re
import threading
import uuid
from decimal import Decimal
from backend.crafting_v11 import Plan, Draft, BaseParameters, digest
from backend.task8_protocol import validate_output, Task8Model, VERSION
from backend.text_review_v11 import fingerprint
from scripts.crafting_compiler_v11 import validate_plan, render_plan, FIELD_MAP
from scripts.native_dependencies_v11 import closure, spell_profile
from backend.resource_names import localized, name_score
from backend.workflow_errors import validation_failure_reason
from scripts.resource_audit_v11 import calls

INCOMPLETE = {'unresolved_questions','display.name:required_for_new_equipment',
              'acquisition:unknown_or_unverified','empty_changes'}
ALIASES = {'治愈真言':'Target_HealingWord','治疗真言':'Target_HealingWord',
           '睡眠':'SLEEPING','睡着':'SLEEPING',
           '治疗光辉':'Shout_HealingRadiance','祝福术':'Target_Bless',
           '魔法飞弹':'Projectile_MagicMissile','繁彩球':'Projectile_ChromaticOrb'}


def normalized_effect(value, effect_id, ids):
    e=copy.deepcopy(value); e['id']=effect_id
    if e['kind']=='bonus':
        if e['bonus']=='resistance':e.setdefault('amount',1)
        elif 'amount' not in e:raise ValueError('bonus_amount_requires_clarification')
    if e['kind']=='trigger':
        if e.get('action','status')!='status':
            if e.get('duration_turns') is not None:
                raise ValueError('instant_effect_has_duration')
            e['duration_turns']=1
        if e.get('status_draft_id'): e['status_draft_id']=ids.get(e['status_draft_id'],e['status_draft_id'])
    if e['kind']=='independent_status':
        if ('ability' in e)!=('amount' in e): raise ValueError('incomplete_ability_pair')
        if not e.get('amount') and not any(b.get('amount',1) for b in e.get('bonuses',[])):
            raise ValueError('empty_status')
        e.setdefault('ability','Strength'); e.setdefault('amount',0)
        e['display']={'name':'独立状态'}
        for index,b in enumerate(e.get('bonuses',[])):
            if b['bonus']=='resistance':b.setdefault('amount',1)
            elif 'amount' not in b:raise ValueError('bonus_amount_requires_clarification')
            b['id']=effect_id+'_bonus_'+str(index)
    return e


def _entry(plan, resources):
    t=resources['templates'][plan.base_equipment.removeprefix('equipment:')]
    return resources['records'][t['stats']]['effective']


def effective_values(plan, resources):
    original=_entry(plan,resources); result={}
    for field in BaseParameters.model_fields:
        raw=original.get(FIELD_MAP.get(field,''))
        if field=='weapon_properties': raw=list(filter(None,original.get('Weapon Properties','').split(';')))
        if field=='dexterity_rule':
            raw=('none' if original.get('Armor Class Ability')=='None' else
                 'capped_2' if original.get('Ability Modifier Cap')=='2' else
                 'full' if original.get('Armor Class Ability')=='Dexterity' else None)
        if field=='enchantment':
            matches=re.findall(r'WeaponEnchantment\((\d+)\)',original.get('DefaultBoosts',''))
            raw=int(matches[0]) if len(matches)==1 else None
        if field in ('weight_kg','armor_class','enchantment','value') and raw is not None:
            try: raw=float(raw) if field=='weight_kg' else int(raw)
            except (ValueError,TypeError): raw=None
        override=getattr(plan.parameters,field)
        result[field]={'original':raw,'current':override if override is not None else raw,
                       'unit':'kg' if field=='weight_kg' else None,'source':'effective_native_fields'}
    return result


def facts(plan, catalog, resources):
    """Pure compiler preview: no disk writes; retain all final dependency records."""
    p=plan.model_copy(deep=True); p.unresolved=[]
    if p.mode=='create_new' and not p.display.name:p.display.name='待命名装备'
    for e in p.effects: e.display.description=None
    inherited={};missing=[]
    native=dict(resources['records'])
    base_name=resources['templates'][p.base_equipment.removeprefix('equipment:')]['stats']
    base=copy.deepcopy(native[base_name]);base['effective']['PassivesOnEquip']=';'.join(
        x for x in base['effective'].get('PassivesOnEquip','').split(';') if x and x not in p.removed_original_passives)
    native[base_name]=base
    try:
        for ref in closure(base_name,native,True):
            if ref!=base_name:inherited[ref]=native[ref]['effective']
    except ValueError as error:missing.append(str(error))
    result=[{'id':'equipment','owner':'equipment','dimensions':{
        'mode':p.mode,'parameters':effective_values(p,resources),
        'inherited_fields':_entry(p,resources),'removed_original_passives':p.removed_original_passives,
        'inherited_dependencies':inherited,
        'acquisition':p.acquisition,'template_behavior':p.template_behavior},'missing':missing}]
    for e in p.effects:
        v=e.model_dump(mode='json');v.pop('display',None)
        v['display_name']=e.display.name or {'grant_spell':'自定义技能','passive_copy':'独立被动'}.get(e.kind,'自定义效果')
        if e.kind=='trigger' and e.action!='status':v.pop('duration_turns',None)
        if e.kind=='independent_status' and e.amount==0:
            v.pop('ability',None);v.pop('amount',None)
        if e.kind in ('constant','bonus','passive_copy','weapon_damage'):v['activation_condition']='装备期间'
        if e.kind=='weapon_damage':
            v['scope']='佩戴者任意武器攻击附加伤害；不作用于队友、徒手或纯法术伤害'
        stacking={'replace':'重复触发刷新持续时间，不累计加成','ignore':'持续期间重复触发不刷新也不叠加','additive':'按独立状态的加法叠加规则处理'}
        if e.kind=='independent_status':v['stacking_explanation']=stacking[e.stacking]
        if e.kind=='trigger' and e.status_draft_id:
            state=next(x for x in p.effects if x.id==e.status_draft_id)
            v['linked_status_stacking']=stacking[state.stacking]
        result.append({'id':'effect_'+e.id,'owner':e.id,'dimensions':v,'missing':[]})
    try:
        files,_=render_plan(p,'00000000-0000-0000-0000-000000000008',catalog=catalog,resources=resources)
        compiled={str(k).replace('\\','/'):(v.decode('utf-8') if isinstance(v,bytes) else v) for k,v in files.items()
                  if str(k).endswith('.txt') and 'Stats' in str(k)}
        result.append({'id':'compiled_dependencies','owner':'equipment',
                       'dimensions':{'final_native_records':compiled},'missing':[]})
    except (ValueError,KeyError) as e:
        if str(e)=='empty_changes' and p.mode=='modify_existing':
            # A first text-only request has not been adopted yet. Mechanics still
            # equal the verified native records; no generated override is needed.
            result.append({'id':'compiled_dependencies','owner':'equipment',
                'dimensions':{'unchanged_native_records':{base_name:base['effective'],**inherited}},'missing':missing})
        else:
            result.append({'id':'compiled_dependencies','owner':'equipment','dimensions':{},'missing':[str(e)]})
    return result


class Task8Session:
    def __init__(self, plan, catalog, resources, *, model=None, inheritance=None):
        self.draft=Draft(plan);self.catalog=catalog;self.resources=resources
        self.model=model or Task8Model();self.lock=threading.RLock()
        self.inheritance='retain_base';self.issues={};self.texts={};self.history=[]
        self.requests={};self.snapshots={};self.log=[];self.goal=plan.user_goal;self.requirements=[]
        self.latest_review=None;self.normalizations=[]
        self.resource_version=fingerprint(resources)
        for n,t in enumerate(plan.unresolved):
            if t!='text_review_pending':self.issues['initial_'+str(n)]={'id':'initial_'+str(n),'detail':t,'kind':'clarification'}
        self._queue_existing_texts()
    def _queue_existing_texts(self):
        """Migrate legacy pending text verbatim; text semantics are not a gate."""
        p=self.draft.plan.model_dump(mode='json')
        for t in self.texts.values():
            owner=t['target']['owner']
            display=p['display'] if owner=='equipment' else next((e['display'] for e in p['effects'] if e['id']==owner),None)
            if display is not None:
                display[t['target']['field']]=None if t['mode']=='reset' else t['text']
        p['unresolved']=[str(i['detail'])[:1500] for i in self.issues.values() if i.get('detail')!='text_review_pending']
        new=Plan.model_validate(p)
        if new!=self.draft.plan:
            self.draft.replace(new,source='manual',expected_revision=self.draft.revision)
        self.texts={};self.latest_review=None

    def candidates(self, text, expanded=False):
        p=self.draft.plan; records=self.resources['records']; refs=set()
        native_passives=set(filter(None,_entry(p,self.resources).get('PassivesOnEquip','').split(';')))
        refs.update(native_passives)
        native_links=set()
        for field in ('WeaponFunctors','BoostsOnEquipMainHand','BoostsOnEquip','DefaultBoosts'):
            try:parsed=calls(_entry(p,self.resources).get(field,''))
            except ValueError:continue  # Raw field stays in context; compiler still validates.
            for function,args in parsed:
                if function in ('ApplyStatus','UnlockSpell') and args:
                    index=1 if args[0] in ('SELF','TARGET','OWNER') else 0
                    if len(args)>index and args[index].strip("'\"") in records:
                        native_links.add(args[index].strip("'\""))
        refs.update(native_links)
        for e in p.effects:
            for k in ('base_spell','base_status','base_passive','status_ref'):
                ref=getattr(e,k,None)
                if ref:refs.add(ref)
        for label,ref in ALIASES.items():
            if label in text:refs.add(ref)
        terms=re.findall(r'[A-Za-z_][A-Za-z0-9_]{3,}',text)
        for ref in records:
            if any(t.casefold() in ref.casefold() for t in terms):refs.add(ref)
        if '状态' in text or '护甲' in text or expanded:refs.add('LONGSTRIDER')
        ranked=[]
        for ref,record in records.items():
            if record['type'] not in ('PassiveData','StatusData','SpellData'):continue
            if re.search(r'(?:^|_)(?:ANIMTEST|TEST)(?:_|$)',ref):continue
            labels=[localized(record['effective'],'DisplayName')]+[label for label,value in ALIASES.items() if value==ref]
            score=max(name_score(label,text,expanded) for label in labels)
            if score:ranked.append((score,ref))
        ranked.sort(key=lambda item:(-item[0],item[1]))
        selected=list(sorted(refs))[:40]
        for score,ref in ranked:
            if ref not in selected and len(selected)<40:selected.append(ref)
        values=[]
        for ref in selected:
            if ref not in records:continue
            r=records[ref]; item={'id':ref,'type':r['type'],'effective':r['effective']}
            item['known_names']=[label for label,value in ALIASES.items() if value==ref]
            name=localized(r['effective'],'DisplayName')
            if name:item['known_names'].append(name)
            item['name']=name or None
            item['description']=localized(r['effective'],'Description')[:800] or None
            item['match_basis']='equipment_or_explicit_reference' if ref in refs else 'localized_name_candidate'
            item['query_match']=any(match_ref==ref for _,match_ref in ranked)
            if ref in native_passives:
                item['equipment_membership']='removed_original' if ref in p.removed_original_passives else 'inherited_original'
            elif ref in native_links:item['equipment_membership']='inherited_reference'
            try:
                item['dependency_count']=len(closure(ref,records,r['type']=='SpellData'))
                if r['type']=='SpellData':item['profile']=spell_profile(ref,records)
            except ValueError as e:item['dependency_issue']=str(e)
            values.append(item)
        values += [{'id':a['id'],'type':'acquisition','limitations':a['limitations']} for a in self.resources['acquisition_entries']]
        values += [{'id':key,'type':'equipment','name':v['display_name']} for key,v in self.catalog['items'].items()
                   if v.get('display_name') and v['display_name'] in text][:20]
        for ref in self.resources['icon_asset_validation']:
            if ref in text and self.resources['icon_asset_validation'][ref].get('asset_exists'):
                values.append({'id':ref,'type':'icon'})
        return values

    def context(self, text, request_id, *, expanded=False, answers=()):
        p=self.draft.plan
        self.resource_version=fingerprint(self.resources)
        key=(p.appearance_equipment or p.base_equipment).removeprefix('equipment:')
        audit=self.resources['body_template_audit']['templates'].get(key,{})
        candidates=self.candidates(text,expanded)
        checks=[{'id':'template_'+fingerprint(audit)[:16],'result':'template_audit',
                 'details':audit.get('special_actions',[])},
                {'id':'check_growth_missing','result':'capability_gap',
                 'details':'当前原生生成规则仅开放 on_hit/on_heal/on_damaged；未实现击杀计数或永久成长规则，不得近似为固定加成。'},
                {'id':'check_ally_aura_missing','result':'capability_gap',
                 'details':'当前没有装备后持续作用于范围队友的可配置光环生成规则：trigger 仅有 on_hit/on_heal/on_damaged，target 仅 self/target，无半径和队友筛选；原生 AuraStatuses 依赖尚未开放。完整光环需求应保留为能力缺口，不得替代为佩戴者命中伤害或主动技能。'}]
        checks += [{'id':'resource_'+fingerprint(v['id'])[:16],'result':'capability_gap',
                    'resource_id':v['id'],'resource_name':v.get('name'),
                    'scope':'仅针对新增引用或独立复制，不否定保留原装备继承效果',
                    'details':'已找到该资源，但原生机制或依赖尚未通过程序检查。不能把此缺口转嫁给玩家，也不能声称更换表述即可支持。',
                    'diagnostic':v['dependency_issue']}
                   for v in candidates if v.get('dependency_issue')]
        c={'request':{'request_id':request_id,'base_revision':self.draft.revision},
           'selection':{'mode':p.mode,'base_equipment':p.base_equipment,'inheritance_strategy':self.inheritance},
           'current_plan':p.model_dump(mode='json'),'effective_values':effective_values(p,self.resources),
           'native_equipment_fields':copy.deepcopy(_entry(p,self.resources)),
           'capabilities':{'version':self.resource_version,'category_summary':['parameters','constant','bonus','weapon_damage','trigger','independent_status','grant_spell','passive_copy','display','resources'],
                           'candidates':candidates,'checks':checks,'completeness':'relevant_candidates_only',
                           'lookup_state':'expanded' if expanded else 'initial'},
           'intent_state':{'goal':self.goal,'requirements':copy.deepcopy(self.requirements),'clarifications':[h for h in self.history if h.get('answers')],
                           'open_issues':list(self.issues.values()),'withdrawn':[]},
           'latest_message':{'id':request_id,'text':text,'answers_issue_ids':list(answers)},
           'recent_history':[{'user':h['user'],'answers':h.get('answers',[]),
               'open_questions':h.get('feedback',{}).get('unresolved',[])} for h in self.history[-3:]],
           'followup_context':{'answer':text,'linked_issues':[
               {'issue':copy.deepcopy(self.issues[i]),
                'original_messages':[h['user'] for h in self.history if any(x.get('id')==i for x in h.get('feedback',{}).get('unresolved',[]))]}
               for i in answers if i in self.issues]},
           'snapshots':[{'id':k,'revision':v['revision']} for k,v in self.snapshots.items()]}
        c['request']['context_digest']=fingerprint(c)
        return c

    def submit(self, text, request_id=None, *, answers=()):
        with self.lock:
            request_id=request_id or str(uuid.uuid4())
            if request_id in self.requests:
                old=self.requests[request_id]
                if old['text']!=text:raise ValueError('request_id_reused')
                return copy.deepcopy(old['result'])
            c=self.context(text,request_id,answers=answers)
            try:
                raw,usage=self.model.run('parse',c)
                self.log.append({'task':'parse','context':c,'output':raw,'usage':usage})
                o=validate_output('parse',raw,c)
                if any(i['kind']=='information_missing' for i in o['issues']):
                    c=self.context(text,request_id,expanded=True,answers=answers)
                    raw,usage=self.model.run('parse',c)
                    self.log.append({'task':'parse_lookup','context':c,'output':raw,'usage':usage})
                    o=validate_output('parse',raw,c)
                result=self.apply(o,c)
                result['assistant_response']=o.get('assistant_response','')
                if c['capabilities']['lookup_state']=='expanded' and any(i['kind']=='information_missing' for i in o['issues']):
                    result['recovery']={
                        'status':'resource_not_found_in_current_catalog',
                        'message':'补查后仍未找到满足这项要求的资源，原需求已保留。可以描述希望实现的触发条件、作用对象、效果和数值，以便检查能否创建独立词条。',
                        'automatic_substitution':False,
                        'requires_user_choice':True,
                        'support_status':'not_yet_validated'}
            except Exception as e:
                self.log.append({'task':'parse_failure','error':getattr(e,'code',str(e)), 'request_id':request_id,'context':c})
                raise
            self.history.append({'user':text,'feedback':result,'answers':list(answers),
                                 'parsed':not(isinstance(usage,dict) and usage.get('recovery')=='pending_requirement')})
            self.requests[request_id]={'text':text,'result':copy.deepcopy(result)}
            return result

    def _operation(self, p, op, ids, c, metadata):
        kind,t,v=op['kind'],op['target'],op['payload']; effects=p['effects']
        working=self.draft.plan
        working.parameters=BaseParameters.model_validate(p['parameters'])
        working.base_equipment=p['base_equipment']
        values=effective_values(working,self.resources)
        def effect():
            found=next((e for e in effects if e['id']==ids.get(t,t)),None)
            if found is None:raise ValueError('unknown_effect:'+t)
            return found
        def arithmetic(base):
            if base is None or isinstance(base,bool):raise ValueError('unknown_relative_basis')
            a,b=Decimal(str(base)),Decimal(str(v['operand']))
            if not a.is_finite() or not b.is_finite():raise ValueError('nonfinite')
            return {'add':lambda:a+b,'subtract':lambda:a-b,'multiply':lambda:a*b}[v['operator']]()
        if kind=='set_parameter':p['parameters'][t]=v['value']
        elif kind=='restore_parameter':p['parameters'][t]=None
        elif kind=='relative_parameter':
            if v['operator']=='multiply' and v['unit'] is not None:raise ValueError('multiply_has_no_unit')
            if t!='weight_kg' and v['unit'] is not None:raise ValueError('wrong_unit')
            n=arithmetic(values[t][v['basis']])
            if t!='weight_kg' and n!=n.to_integral_value():raise ValueError('integer_required')
            p['parameters'][t]=float(n) if t=='weight_kg' else int(n)
        elif kind=='edit_weapon_properties':
            if set(v['add']) & set(v['remove']):raise ValueError('conflicting_property_operation')
            p['parameters'][t]=sorted((set(values[t]['current'])|set(v['add']))-set(v['remove']))
        elif kind=='add_effect':
            if any(e['id']==ids[t] for e in effects):raise ValueError('duplicate_effect')
            for ref_field in ('base_spell','base_status','base_passive','status_ref'):
                ref=v['effect'].get(ref_field)
                if ref and ref not in {x['id'] for x in c['capabilities']['candidates']}:raise ValueError('reference_not_in_context:'+ref_field)
            effects.append(normalized_effect(v['effect'],ids[t],ids))
        elif kind=='update_effect':
            e=effect()
            if e['kind']!=v['effect_kind']:raise ValueError('wrong_effect_kind')
            changes=copy.deepcopy(v['changes'])
            for ref_field in ('base_spell','base_status','base_passive','status_ref'):
                ref=changes.get(ref_field)
                if ref and ref not in {x['id'] for x in c['capabilities']['candidates']}:raise ValueError('reference_not_in_context:'+ref_field)
            if e['kind']=='trigger' and changes.get('action',e.get('action'))!='status' and changes.get('duration_turns') is not None:
                raise ValueError('instant_effect_has_duration')
            if e['kind']=='independent_status' and 'bonuses' in changes:
                for i,b in enumerate(changes['bonuses']):
                    if b['bonus']=='resistance':b.setdefault('amount',1)
                    elif 'amount' not in b:raise ValueError('bonus_amount_requires_clarification')
                    b['id']=e['id']+'_bonus_'+str(i)
            e.update(changes)
            if e.get('status_draft_id'):e['status_draft_id']=ids.get(e['status_draft_id'],e['status_draft_id'])
        elif kind=='relative_effect':
            e=effect();field=v['field'];base=e.get(field)
            if field not in e or (e['kind']=='bonus' and e['bonus']=='resistance'):raise ValueError('relative_effect_basis_unavailable')
            if v['basis']=='original' or (base is None and e['kind']=='grant_spell'):
                if e['kind']!='grant_spell':raise ValueError('relative_effect_basis_unavailable')
                original=self.resources['records'][e['base_spell']]['effective']
                native_field={'range_m':'TargetRadius','area_radius_m':'AreaRadius'}.get(field)
                if not native_field or native_field not in original:raise ValueError('relative_effect_basis_unavailable')
                base=original[native_field]
            if e['kind']=='trigger' and e.get('action')!='status' and field=='duration_turns':raise ValueError('instant_effect_has_duration')
            n=arithmetic(base)
            if field not in ('range_m','area_radius_m') and n!=n.to_integral_value():raise ValueError('integer_required')
            e[field]=float(n) if field in ('range_m','area_radius_m') else int(n)
        elif kind=='remove_effect':effects.remove(effect())
        elif kind=='remove_original_passive':
            if t not in p['removed_original_passives']:p['removed_original_passives'].append(t)
        elif kind=='restore_original_passive':
            if t not in p['removed_original_passives']:raise ValueError('passive_not_removed')
            p['removed_original_passives'].remove(t)
        elif kind=='select_reference':
            ref=v['reference_id']
            if ref is not None and ref not in {x['id'] for x in c['capabilities']['candidates']}:
                raise ValueError('reference_not_in_context')
            p[t]=ref
        elif kind=='set_inheritance_intent':
            if p['mode']!='create_new':raise ValueError('inheritance_only_for_creation')
            metadata['inheritance']='retain_base'  # Legacy intent never clears inherited effects.
        elif kind=='set_template_behavior':
            if v['audit_id'] not in {x['id'] for x in c['capabilities']['checks'] if x.get('result')=='template_audit'}:raise ValueError('stale_template_audit')
            p['template_behavior']=v['value']
        elif kind=='change_context':
            if v['base_equipment'] not in {x['id'] for x in c['capabilities']['candidates']}:raise ValueError('unknown_base_selection')
            if v['carry_policy']=='reset':
                p.update(parameters={},effects=[],removed_original_passives=[],display={},appearance_equipment=None,icon=None,acquisition=None,template_behavior='reject_special')
                metadata['reset_context']=True
            p.update(mode=v['mode'],base_equipment=v['base_equipment'],template_behavior='reject_special')
            metadata['inheritance']='retain_base'
        elif kind=='restore_snapshot':
            snap=self.snapshots.get(v['snapshot_id'])
            if not snap or (snap['plan']['mode'],snap['plan']['base_equipment'])!=(p['mode'],p['base_equipment']):raise ValueError('snapshot_context_mismatch')
            p.clear();p.update(copy.deepcopy(snap['plan']));metadata['inheritance']='retain_base'
            metadata['restore']=snap
        else:raise ValueError('unknown_operation')

    def apply(self, output, context):
        with self.lock:
            o=validate_output('parse',output,context)
            if self.draft.revision!=context['request']['base_revision'] or context['current_plan']!=self.draft.plan.model_dump(mode='json'):
                raise ValueError('stale_draft')
            if context['capabilities']['version']!=fingerprint(self.resources):raise ValueError('stale_resources')
            if self.draft.state=='generating':raise ValueError('generation_in_progress')
            old=self.draft.plan; p=old.model_dump(mode='json'); p['unresolved']=[]
            issues=copy.deepcopy(self.issues);texts=copy.deepcopy(self.texts)
            metadata={'inheritance':self.inheritance};ids={}
            for op in o['operations']:
                if op['kind']=='add_effect':ids[op['target']]='e_'+uuid.uuid5(uuid.NAMESPACE_URL,context['request']['request_id']+':'+op['target']).hex
            # Merge groups by target/reference; dependency-connected changes commit together.
            groups={}
            for op in o['operations']:groups.setdefault(op['group_id'],[]).append(op)
            def touched(ops):
                keys=set()
                for op in ops:
                    keys.add(op['target']);v=op['payload'];e=v.get('effect',v.get('changes',{}))
                    if e.get('status_draft_id'):keys.add(e['status_draft_id'])
                    if e.get('base_passive'):keys.add(e['base_passive'])
                    existing=next((x for x in p['effects'] if x['id']==op['target']),{})
                    if existing.get('status_draft_id'):keys.add(existing['status_draft_id'])
                    if existing.get('base_passive'):keys.add(existing['base_passive'])
                return keys
            merged=list(groups.values());changed=True
            while changed:
                changed=False
                for a in range(len(merged)):
                    for b in range(a+1,len(merged)):
                        if touched(merged[a]) & touched(merged[b]):
                            merged[a]+=merged.pop(b);changed=True;break
                    if changed:break
            applied=[];failed=[]
            for group in merged:
                candidate=copy.deepcopy(p);meta=copy.deepcopy(metadata)
                try:
                    writes=set()
                    for op in group:
                        fields=list(op['payload'].get('changes',{})) or ([op['payload']['field']] if op['kind']=='relative_effect' else ['value'])
                        for field in fields:
                            key=(op['target'],field)
                            if key in writes:raise ValueError('conflicting_writes')
                            writes.add(key)
                        self._operation(candidate,op,ids,context,meta)
                    proposed=Plan.model_validate(candidate)
                    checks=validate_plan(proposed,self.catalog,self.resources)
                    errors=[x for x in checks if x not in INCOMPLETE]
                    if errors:raise ValueError(';'.join(errors))
                    p=proposed.model_dump(mode='json');metadata=meta;applied += [op['id'] for op in group]
                except (ValueError,KeyError,TypeError) as e:
                    key='failed_'+context['request']['request_id']+'_'+group[0]['id']
                    detail=str(e)[:1000];failed.append({'operations':[op['id'] for op in group],'error':detail})
                    issues[key]={'id':key,'kind':'capability_gap','detail':validation_failure_reason(detail),
                                 'requirements':[r['quote'] for r in o['requirements'] if set(r['operation_ids']) & {x['id'] for x in group}]}
            if metadata.get('restore'):
                issues=copy.deepcopy(metadata['restore']['issues'])
                texts=copy.deepcopy(metadata['restore']['texts'])
            if metadata.get('reset_context'):
                for key,t in texts.items():
                    issues['reconsider_'+key]={'id':'reconsider_'+key,'kind':'clarification',
                        'detail':'对象已切换，旧文案要求需要重新定位或明确撤回','previous_text_request':t}
                texts={}
            for i in o['issues']:
                key=context['request']['request_id']+'_'+i['id'];issues[key]=dict(i,id=key)
            applied_texts=set()
            for t in o['text_requests']:
                owner=ids.get(t['target']['owner'],t['target']['owner'])
                if owner!='equipment' and owner not in {e['id'] for e in p['effects']}:
                    key='text_target_'+t['id'];issues[key]={'id':key,'kind':'clarification','detail':'文字目标尚未成功建立','request':t};continue
                target=p['display'] if owner=='equipment' else next(e['display'] for e in p['effects'] if e['id']==owner)
                field=t['target']['field'];key=owner+':'+field
                if t['mode']=='reset':
                    target[field]=None;texts.pop(key,None)
                else:
                    target[field]=t['text'];texts.pop(key,None)
                applied_texts.add(t['id'])
            for u in o['issue_updates']:
                if u['proposed_action']=='withdrawn' or (set(u['operation_ids'])<=set(applied) and set(u['text_request_ids'])<=applied_texts):
                    issues.pop(u['issue_id'],None)
            metadata['inheritance']='retain_base'
            issues.pop('inheritance',None)
            texts={k:t for k,t in texts.items() if t['target']['owner']=='equipment' or t['target']['owner'] in {e['id'] for e in p['effects']}}
            blockers=[str(i['detail'])[:1500] for i in issues.values()]
            if len(blockers)>20:raise ValueError('too_many_unresolved_requirements')
            p['unresolved']=blockers
            new=Plan.model_validate(p)
            snapshot='snapshot_'+str(self.draft.revision)
            self.snapshots[snapshot]={'revision':self.draft.revision,'plan':old.model_dump(mode='json'),'inheritance':self.inheritance,
                                      'issues':copy.deepcopy(self.issues),'texts':copy.deepcopy(self.texts)}
            self.draft.replace(new,source='ai',expected_revision=self.draft.revision)
            self.issues,self.texts,self.inheritance=issues,texts,metadata['inheritance'];self.latest_review=None
            self.requirements += [{'request_id':context['request']['request_id'],**copy.deepcopy(r)} for r in o['requirements']]
            self._queue_existing_texts()
            normalizations=[]
            for op in o['operations']:
                if op['id'] not in applied or op['kind']!='add_effect':continue
                effect=op['payload']['effect']
                if effect['kind']=='trigger' and effect.get('action') in ('damage','heal'):
                    normalizations.append({'effect_id':ids[op['target']],'rule':'instant_duration_unused','technical_value':1})
                if effect['kind']=='independent_status' and 'ability' not in effect:
                    normalizations.append({'effect_id':ids[op['target']],'rule':'zero_ability_compat','technical_amount':0})
            self.normalizations.extend(normalizations)
            return {'revision':self.draft.revision,'applied':applied,'failed':failed,
                    'normalizations':normalizations,
                    'before':old.model_dump(mode='json'),'after':self.draft.plan.model_dump(mode='json'),
                    'unresolved':copy.deepcopy(list(issues.values())),'text_review_pending':bool(texts)}

    def review_context(self):
        f=facts(self.draft.plan,self.catalog,self.resources);texts=[]
        for key,t in self.texts.items():
            owner=t['target']['owner'];required=[x['id'] for x in f if x['owner']==owner]
            if owner!='equipment':required.append('compiled_dependencies')
            texts.append({'id':key,'owner':owner,'field':t['target']['field'],'mode':t['mode'],
                          'source_text':t['text'],'source_text_digest':fingerprint(t['text']),
                          'style':t['style'],'required_fact_ids':required})
        c={'request':{'request_id':str(uuid.uuid4()),'base_revision':self.draft.revision},
           'resource_digest':fingerprint(self.resources),
           'plan_digest':digest(self.draft.plan),'facts_digest':fingerprint(f),'facts':f,'texts':texts}
        c['request']['context_digest']=fingerprint(c)
        return c

    def review_text(self):
        # Compatibility endpoint: adopt supplied text without a model consistency check.
        with self.lock:
            self._queue_existing_texts()
            return self.preview()

    def apply_review(self, output, context):
        # Old clients may still send review results. They cannot replace user text.
        return self.review_text()

    def adopt_review(self, *, replacements=()):
        return self.review_text()

    def use_standard_text(self):
        """Explicit user recovery: discard custom descriptions, not unresolved requirements."""
        with self.lock:
            p=self.draft.plan
            for t in self.texts.values():
                owner=t['target']['owner'];display=p.display if owner=='equipment' else next(e.display for e in p.effects if e.id==owner)
                if t['target']['field']=='name':display.name='新装备' if owner=='equipment' and p.mode=='create_new' else None
                elif t['target']['field']=='description':display.description=None
            p.unresolved=[str(x['detail'])[:1500] for x in self.issues.values()]
            self.draft.replace(p,source='manual',expected_revision=self.draft.revision)
            self.texts={};self.latest_review=None
            return self.draft.review(self.catalog,self.resources)

    def preview(self):
        with self.lock:
            if self.texts or self.issues:raise ValueError('unresolved_requirements_or_text')
            errors=self.draft.review(self.catalog,self.resources,text_receipt=self.draft.text_receipt)
            return {'revision':self.draft.revision,'digest':digest(self.draft.plan),'issues':errors,
                    'plan':self.draft.plan.model_dump(mode='json')}

    def confirm(self, *, expected_revision, expected_digest):
        with self.lock:
            if self.texts or self.issues:raise ValueError('unresolved_requirements_or_text')
            if self.draft.review(self.catalog,self.resources,text_receipt=self.draft.text_receipt):
                raise ValueError('capability_review_failed')
            self.draft.confirm(expected_revision=expected_revision,expected_digest=expected_digest)
