"""Independent task8 acceptance: inputs authored without the prompt example outputs."""
import copy
import json
import unittest
import uuid
from backend.crafting_v11 import Plan, Draft, digest
from backend.task8 import Task8Session
from scripts.crafting_compiler_v11 import load_resources, render_plan, check_files
from scripts.equipment_catalog import load_catalog
from scripts.generate_mod import ROOT


def operation(kind,target,payload,group='g'):
    return dict(kind=kind,target=target,payload=payload,group_id=group)


def output(session,ops=(),texts=(),issues=(),updates=(),message='独立验收：接受保留，取消旧要求，改为当前方案'):
    c=session.context(message,str(uuid.uuid4()),expanded=True)
    ops=[dict(x,id='op'+str(i),requirement_ids=['r']) for i,x in enumerate(ops)]
    texts=[dict(x,id='txt'+str(i),requirement_ids=['r']) for i,x in enumerate(texts)]
    issues=[dict(x,id='issue'+str(i),requirement_ids=['r']) for i,x in enumerate(issues)]
    r=dict(id='r',quote=message,meaning=message,operation_ids=[x['id'] for x in ops],text_request_ids=[x['id'] for x in texts],
           issue_ids=[x['id'] for x in issues],issue_update_ids=[x['id'] for x in updates],no_change=not(ops or texts or issues or updates))
    return dict(schema_version='parse-v1',**c['request'],intent_summary=message,requirements=[r],operations=ops,
                text_requests=texts,issues=issues,issue_updates=list(updates)),c


def review(session, conflict=False):
    c=session.review_context()
    items=[]
    for t in c['texts']:
        source=t['source_text']
        items.append(dict(text_id=t['id'],source_text_digest=t['source_text_digest'],
            source_status='conflict' if conflict else 'consistent' if source else 'not_provided',
            findings=[dict(dimension='condition',quote=None,fact_refs=t['required_fact_ids'],explanation='独立检查冲突')] if conflict else [],
            proposed_text='装备期间生效。' if conflict or t['mode']=='rewrite' else None,
            proposal_status='consistent' if conflict or t['mode']=='rewrite' else 'not_requested',proposal_findings=[]))
    return dict(schema_version='review-v1',**c['request'],plan_digest=c['plan_digest'],items=items),c


class IndependentAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources=load_resources();cls.catalog=load_catalog()
        cls.fixtures=json.loads((ROOT/'data/v1.1/phase-b-cases.json').read_text(encoding='utf-8'))

    def session(self,key='create_weapon',mode=None,keep=False):
        p=copy.deepcopy(self.fixtures[key])
        if not keep:p.update(parameters={},effects=[],display={})
        if mode:p['mode']=mode
        if p['mode']=='modify_existing':p.update(acquisition=None,appearance_equipment=None)
        return Task8Session(Plan.model_validate(p),self.catalog,self.resources,inheritance='retain_base')

    def apply(self,s,ops=(),texts=(),issues=(),updates=(),message='独立验收：接受保留，取消旧要求，改为当前方案'):
        o,c=output(s,ops,texts,issues,updates,message)
        # Fixtures use actual native references, never invented IDs.
        for op in ops:
            v=op['payload'];e=v.get('effect',v.get('changes',{}))
            for field in ('base_spell','base_status','base_passive','status_ref'):
                if e.get(field):c['capabilities']['candidates'].append({'id':e[field]})
            if op['kind']=='select_reference' and v['reference_id']:c['capabilities']['candidates'].append({'id':v['reference_id']})
            if op['kind']=='change_context':c['capabilities']['candidates'].append({'id':v['base_equipment']})
        return s.apply(o,c)

    def test_native_passive_context_distinguishes_inherited_removed_and_added(self):
        s=self.session('passive_copy',mode='modify_existing')
        p=s.draft.plan;p.removed_original_passives=[];s.draft=Draft(p)
        self.assertFalse(s.draft.plan.effects)
        def candidate():
            return next(x for x in s.context('保留原生效果','native')['capabilities']['candidates'] if x['id']=='ARM_Balance_1_Passive')
        self.assertEqual(candidate()['equipment_membership'],'inherited_original')
        # Native DisplayName hfa195d11gb383g4f2fg9d6ag948e8cdf8bcd;2 resolves to 平衡.
        self.assertEqual(candidate()['known_names'],['平衡'])
        self.assertFalse(self.apply(s,[operation('remove_original_passive','ARM_Balance_1_Passive',{})])['failed'])
        self.assertEqual(candidate()['equipment_membership'],'removed_original')

    def test_ten_parameters_set_restore_in_both_modes(self):
        fields={'damage':'3d4','versatile_damage':'3d6','damage_type':'Cold','weight_kg':2.345,'rarity':'VeryRare',
                'value':742,'enchantment':3,'weapon_properties':['Versatile','Melee','Dippable','Light'],
                'armor_class':19,'dexterity_rule':'capped_2'}
        for mode in ('modify_existing','create_new'):
            for field,value in fields.items():
                with self.subTest(mode=mode,field=field):
                    s=self.session('create_body_armor' if field in ('armor_class','dexterity_rule') else 'create_weapon',mode)
                    result=self.apply(s,[operation('set_parameter',field,{'value':value,'unit':'kg' if field=='weight_kg' else None})])
                    self.assertFalse(result['failed'],result)
                    self.assertEqual(getattr(s.draft.plan.parameters,field),value)
                    self.assertFalse(self.apply(s,[operation('restore_parameter',field,{})])['failed'])
                    self.assertIsNone(getattr(s.draft.plan.parameters,field))

    def test_six_effects_add_update_delete_both_modes(self):
        for mode in ('modify_existing','create_new'):
            for kind in ('constant','bonus','trigger','independent_status','grant_spell','passive_copy'):
                with self.subTest(mode=mode,kind=kind):
                    s=self.session('passive_copy' if kind=='passive_copy' else 'create_weapon',mode)
                    source=self.fixtures['passive_copy' if kind=='passive_copy' else 'create_weapon']['effects']
                    chosen=[next(copy.deepcopy(e) for e in source if e['kind']==kind)]
                    if kind=='trigger':chosen=[dict(kind='trigger',id='t',event='on_hit',condition='always',target='self',action='heal',dice='2d6')]
                    if kind=='independent_status':chosen += [next(copy.deepcopy(e) for e in source if e.get('status_draft_id'))]
                    ops=[]
                    if kind=='passive_copy':ops.append(operation('remove_original_passive',chosen[0]['base_passive'],{}))
                    for e in chosen:
                        key=e.pop('id');e.pop('display',None)
                        if e['kind']=='trigger' and e['action']!='status':e.pop('duration_turns',None)
                        ops.append(operation('add_effect',key,{'effect':e}))
                    self.assertFalse(self.apply(s,ops)['failed'])
                    p=s.draft.plan;main=next(e for e in p.effects if e.kind==kind)
                    change={'constant':{'amount':4},'bonus':{'amount':4},'trigger':{'dice':'3d6'},
                            'independent_status':{'stacking':'additive'},'grant_spell':{'range_m':28},'passive_copy':{'base_passive':main.base_passive if kind=='passive_copy' else ''}}[kind]
                    self.assertFalse(self.apply(s,[operation('update_effect',main.id,{'effect_kind':kind,'changes':change})])['failed'])
                    compiled=s.draft.plan;compiled.unresolved=[]
                    if mode=='create_new':compiled.display.name='独立验收装备';compiled.acquisition='dammon_act1'
                    files,manifest=render_plan(compiled,str(uuid.uuid4()),catalog=self.catalog,resources=self.resources);check_files(files,manifest,self.resources)
                    ops=[operation('remove_effect',e.id,{}) for e in s.draft.plan.effects]
                    self.assertFalse(self.apply(s,ops)['failed']);self.assertEqual(s.draft.plan.effects,[])

    def test_all_bonus_subtypes_and_nested_status_updates(self):
        for bonus,selector in [('initiative',None),('movement',None),('armor_class',None),('skill','Arcana'),('saving_throw','Charisma'),('resistance','Cold')]:
            s=self.session();e=dict(kind='bonus',bonus=bonus,selector=selector,amount=1)
            self.assertFalse(self.apply(s,[operation('add_effect','b',{'effect':e})])['failed'])
        s=self.session('independent_status',keep=True)
        self.assertFalse(self.apply(s,[operation('update_effect','s',{'effect_kind':'independent_status','changes':{'bonuses':[dict(kind='bonus',bonus='movement',amount=2,selector=None)]}})])['failed'])
        self.assertEqual(s.draft.plan.effects[0].bonuses[0].amount,2)

    def test_status_duration_relative_and_dependency_atomicity(self):
        s=self.session('independent_status',keep=True)
        ops=[operation('relative_effect',key,dict(field='duration_turns',operator='add',operand=1,basis='current'),key) for key in ('s','t')]
        r=self.apply(s,ops);self.assertFalse(r['failed']);self.assertTrue(all(e.duration_turns==3 for e in s.draft.plan.effects))
        before=digest(s.draft.plan)
        r=self.apply(s,[operation('remove_effect','s',{})]);self.assertTrue(r['failed']);self.assertEqual(len(s.draft.plan.effects),2)

    def test_relative_effect_uses_inherited_spell_value(self):
        s=self.session();self.apply(s,[operation('add_effect','h',{'effect':{'kind':'grant_spell','base_spell':'Target_HealingWord'}})])
        e=s.draft.plan.effects[0]
        r=self.apply(s,[operation('relative_effect',e.id,dict(field='range_m',operator='add',operand=2,basis='current'))])
        self.assertFalse(r['failed'],r);self.assertIsNotNone(s.draft.plan.effects[0].range_m)

    def test_context_reset_does_not_reapply_old_pending_text(self):
        s=self.session('create_weapon',keep=True)
        text='旧对象说明';self.apply(s,texts=[dict(target={'owner':'equipment','field':'description'},mode='exact',text=text,style=None)],message=text)
        r=self.apply(s,[operation('change_context','equipment',dict(mode='create_new',base_equipment=self.fixtures['create_body_armor']['base_equipment'],carry_policy='reset',evidence_quote='接受保留'))])
        self.assertFalse(r['failed'],r)
        self.assertNotIn('equipment:description',s.texts)
        self.assertTrue(s.issues,'Old user intent must remain blocked pending reassessment')

    def test_resource_change_between_review_and_adoption_rejected(self):
        s=self.session();self.apply(s,texts=[dict(target={'owner':'equipment','field':'description'},mode='exact',text='永久效果',style=None)],message='永久效果')
        o,c=review(s,True);s.apply_review(o,c);s.resources=dict(s.resources,acceptance_revision='changed')
        with self.assertRaisesRegex(ValueError,'stale_review'):s.adopt_review(replacements=['equipment:description'])

    def test_text_same_target_conflict_rejected(self):
        s=self.session();texts=[dict(target={'owner':'equipment','field':'name'},mode='exact',text=t,style=None) for t in ('甲','乙')]
        before=digest(s.draft.plan)
        with self.assertRaisesRegex(ValueError,'conflicting_text'):self.apply(s,texts=texts,message='名称甲或乙')
        self.assertEqual(digest(s.draft.plan),before)

    def test_relative_parameter_precision_rejects_without_clipping(self):
        s=self.session();self.apply(s,[operation('set_parameter','weight_kg',{'value':.001,'unit':'kg'})])
        r=self.apply(s,[operation('relative_parameter','weight_kg',dict(operator='multiply',operand=.5,basis='current',unit=None))])
        self.assertTrue(r['failed']);self.assertEqual(s.draft.plan.parameters.weight_kg,.001)

    def test_reset_rewrite_standard_and_confirmation_invalidation(self):
        s=self.session(mode='modify_existing');self.apply(s,[operation('set_parameter','value',dict(value=73,unit=None))])
        self.apply(s,texts=[dict(target={'owner':'equipment','field':'description'},mode='rewrite',text=None,style='朴素')])
        o,c=review(s);s.apply_review(o,c);self.assertEqual(s.draft.plan.display.description,'装备期间生效。')
        self.apply(s,texts=[dict(target={'owner':'equipment','field':'description'},mode='reset',text=None,style=None)])
        self.assertIsNone(s.draft.plan.display.description)
        s.use_standard_text();p=s.preview();s.confirm(expected_revision=p['revision'],expected_digest=p['digest'])
        self.apply(s,[operation('set_parameter','value',dict(value=74,unit=None))]);self.assertIsNone(s.draft.confirmation)

    def test_all_review_targets_and_resource_selection(self):
        s=self.session('create_body_armor')
        for target,ref in [('appearance_equipment',self.fixtures['armor_appearance_swap']['appearance_equipment']),('acquisition','dammon_act1')]:
            self.assertFalse(self.apply(s,[operation('select_reference',target,dict(reference_id=ref))])['failed'])
        icon=next(k for k,v in self.resources['icon_asset_validation'].items() if v.get('asset_exists'))
        self.assertFalse(self.apply(s,[operation('select_reference','icon',dict(reference_id=icon))])['failed'])
        self.assertFalse(self.apply(s,[operation('select_reference','icon',dict(reference_id=None))])['failed'])

    def test_issue_lifecycle_independent_success_and_withdrawal(self):
        s=self.session('create_body_armor')
        self.apply(s,issues=[dict(kind='clarification',detail='需要明确价值',question='价值多少？',options=[],evidence_refs=[])])
        issue=next(iter(s.issues));update=dict(id='u',issue_id=issue,proposed_action='answered',evidence_quote='接受保留',operation_ids=['op0'],text_request_ids=[])
        result=self.apply(s,[operation('set_parameter','value',dict(value=123,unit=None),'good'),operation('set_parameter','damage',dict(value='4d4',unit=None),'bad')],updates=[update])
        self.assertTrue(result['failed']);self.assertNotIn(issue,s.issues);self.assertEqual(s.draft.plan.parameters.value,123)
        issue=next(iter(s.issues));update=dict(id='u',issue_id=issue,proposed_action='withdrawn',evidence_quote='取消旧要求',operation_ids=[],text_request_ids=[])
        self.apply(s,updates=[update]);self.assertFalse(s.issues)

    def test_inheritance_reconfigure_can_be_resolved_without_erasing_base(self):
        s=self.session();s.inheritance=None
        self.apply(s,[operation('set_inheritance_intent','equipment',dict(strategy='reconfigure'))]);self.assertIn('inheritance',s.issues)
        update=dict(id='u',issue_id='inheritance',proposed_action='answered',evidence_quote='接受保留',operation_ids=['op0'],text_request_ids=[])
        self.apply(s,[operation('set_parameter','value',dict(value=111,unit=None))],updates=[update],message='接受保留原版所有其他参数与效果，只将价值改为111')
        self.assertNotIn('inheritance',s.issues);self.assertEqual(s.draft.plan.removed_original_passives,[])

    def test_special_template_ack_is_bound_to_current_audit(self):
        s=self.session('special_gale_template')
        o,c=output(s,message='接受保留已审核的盖尔消耗行为')
        op=operation('set_template_behavior','equipment',dict(value='preserve_reviewed',audit_id=c['capabilities']['checks'][0]['id'],evidence_quote=c['latest_message']['text']))
        o,c=output(s,[op],message=c['latest_message']['text']);self.assertFalse(s.apply(o,c)['failed'])
        self.assertEqual(s.draft.plan.template_behavior,'preserve_reviewed')
        op['payload']['audit_id']='stale_audit';self.assertTrue(self.apply(s,[op],message='接受保留已审核的盖尔消耗行为')['failed'])

    def test_restore_original_passive_and_remove_copy_together(self):
        s=self.session('passive_copy',keep=True);old=s.draft.plan.effects[0]
        self.assertFalse(self.apply(s,[operation('remove_effect',old.id,{},'one'),operation('restore_original_passive',old.base_passive,{},'two')])['failed'])
        self.assertFalse(s.draft.plan.effects);self.assertFalse(s.draft.plan.removed_original_passives)

    def test_spell_profiles_delay_container_costs_are_compiled(self):
        for fixture in ('status_spell_upcasts','delayed_heal','damage_spell','container_spell'):
            with self.subTest(fixture=fixture):
                s=self.session(fixture,keep=True);spell=next(e for e in s.draft.plan.effects if e.kind=='grant_spell')
                self.assertFalse(self.apply(s,[operation('update_effect',spell.id,dict(effect_kind='grant_spell',changes={'cooldown':'short_rest'}))])['failed'])
                p=s.draft.plan;p.unresolved=[]
                f,m=render_plan(p,str(uuid.uuid4()),catalog=self.catalog,resources=self.resources);check_files(f,m,self.resources)
                rc=s.review_context();self.assertFalse([x for x in rc['facts'] if x['missing']])

    def test_timeout_retry_does_not_apply_partial_changes(self):
        s=self.session();before=digest(s.draft.plan)
        class Broken:
            def run(self,*args):raise TimeoutError('fixture timeout')
        s.model=Broken()
        with self.assertRaises(TimeoutError):s.submit('价值修改为88','retry')
        self.assertEqual(digest(s.draft.plan),before);self.assertNotIn('retry',s.requests)
        class Working:
            def run(self,task,c):
                o,_=output(s,[operation('set_parameter','value',dict(value=88,unit=None))],message='价值修改为88');o.update(c['request']);return o,None
        s.model=Working();s.submit('价值修改为88','retry');self.assertEqual(s.draft.plan.parameters.value,88)

    def test_invalid_types_bounds_and_unknown_fields_rejected(self):
        s=self.session();before=digest(s.draft.plan)
        for field,value in [('weight_kg',-1),('armor_class',31),('value',True),('enchantment',6),('rarity','Mythic'),('damage','100d100')]:
            with self.subTest(field=field),self.assertRaises(ValueError):self.apply(s,[operation('set_parameter',field,dict(value=value,unit='kg' if field=='weight_kg' else None))])
        self.assertEqual(digest(s.draft.plan),before)

    def test_context_revalidate_and_stale_response(self):
        s=self.session(mode='modify_existing');self.apply(s,[operation('set_parameter','value',dict(value=222,unit=None))])
        o,c=output(s,[operation('set_parameter','value',dict(value=333,unit=None))])
        self.apply(s,[operation('change_context','equipment',dict(mode='modify_existing',base_equipment=self.fixtures['create_body_armor']['base_equipment'],carry_policy='revalidate',evidence_quote='接受保留'))])
        self.assertEqual(s.draft.plan.parameters.value,222)
        with self.assertRaisesRegex(ValueError,'stale_draft'):s.apply(o,c)

    def test_parse_resource_change_rejects_old_relative_basis(self):
        s=self.session();o,c=output(s,[operation('relative_parameter','weight_kg',dict(operator='multiply',operand=2,basis='current',unit=None))])
        s.resources=dict(s.resources,acceptance_revision='changed')
        with self.assertRaisesRegex(ValueError,'stale_resources'):s.apply(o,c)

    def test_remaining_spell_fields_and_profile_rejections(self):
        for source,changes in [('Shout_HealingRadiance',dict(healing='3d4',area_radius_m=7)),
                               ('Projectile_FireBolt',dict(damage='3d6',range_m=25,action_cost='bonus_action',cooldown='once_per_turn')),
                               ('Target_Bless',dict(status_duration_turns=4,spell_slot={'level':3,'amount':1}))]:
            s=self.session();self.apply(s,[operation('add_effect','spell',{'effect':dict(kind='grant_spell',base_spell=source)})])
            key=s.draft.plan.effects[0].id
            self.assertFalse(self.apply(s,[operation('update_effect',key,dict(effect_kind='grant_spell',changes=changes))])['failed'])
            self.assertTrue(self.apply(s,[operation('update_effect',key,dict(effect_kind='grant_spell',changes={'base_spell':'UNKNOWN_SPELL'}))])['failed'])

    def test_trigger_combinations_reject_recursive_and_preserve_condition(self):
        for event,action,target,valid in [('on_hit','damage','target',True),('on_damaged','heal','self',True),('on_heal','heal','self',False),('on_damaged','damage','target',False)]:
            s=self.session();e=dict(kind='trigger',event=event,condition='target_full_health' if event=='on_hit' else 'always',action=action,target=target,dice='2d4')
            if action=='damage':e['damage_type']='Cold'
            result=self.apply(s,[operation('add_effect','t',{'effect':e})]);self.assertEqual(not result['failed'],valid,result)
            if valid:self.assertEqual(s.draft.plan.effects[0].condition,e['condition'])

    def test_missing_inherited_facts_cannot_receive_text_receipt(self):
        s=self.session('modify_existing');r=copy.deepcopy(self.resources)
        base=r['templates'][s.draft.plan.base_equipment.removeprefix('equipment:')]['stats']
        r['records'][base]['effective']['PassivesOnEquip']='MISSING_ACCEPTANCE_PASSIVE';s.resources=r
        self.apply(s,texts=[dict(target={'owner':'equipment','field':'description'},mode='exact',text='普通说明',style=None)],message='普通说明')
        o,c=review(s)
        self.assertTrue(any(f['missing'] for f in c['facts']))
        with self.assertRaisesRegex(ValueError,'effective_facts_incomplete'):s.apply_review(o,c)

    def test_null_instant_duration_normalizes_but_status_null_rejects(self):
        s=self.session();e=dict(kind='trigger',event='on_hit',condition='always',target='self',action='heal',dice='2d4',duration_turns=None)
        result=self.apply(s,[operation('add_effect','t',{'effect':e})]);self.assertFalse(result['failed']);self.assertEqual(result['normalizations'][0]['rule'],'instant_duration_unused')
        e.update(action='status',dice=None,status_ref='LONGSTRIDER')
        self.assertTrue(self.apply(s,[operation('add_effect','status_t',{'effect':e})])['failed'])


if __name__=='__main__':unittest.main()
