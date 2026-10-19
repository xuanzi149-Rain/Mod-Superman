import copy
import json
import unittest
import uuid
from backend.crafting_v11 import Plan, Draft, digest
from backend.task8 import Task8Session, normalized_effect, facts
from backend.task8_protocol import validate_output, examples, schema, messages
from backend.text_review_v11 import fingerprint, TextReceipt
from scripts.crafting_compiler_v11 import load_resources, render_plan, validate_plan
from scripts.equipment_catalog import load_catalog
from scripts.generate_mod import ROOT


class Task8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources=load_resources();cls.catalog=load_catalog()
        cls.cases=json.loads((ROOT/'data/v1.1/phase-b-cases.json').read_text(encoding='utf-8'))

    def session(self,key='modify_existing'):
        p=copy.deepcopy(self.cases[key]);p.update(parameters={},effects=[],removed_original_passives=[],display={})
        return Task8Session(Plan.model_validate(p),self.catalog,self.resources,inheritance='retain_base')

    def response(self,s,example='E01',text=None):
        e=next(e for e in examples()['parse_examples'] if e['id']==example)
        c=s.context(text or e['input']['latest_message']['text'],'test_'+example)
        o=copy.deepcopy(e['expected_output']);o.update(c['request'])
        return o,c

    def test_all_spec_examples_structural_and_semantic(self):
        for task in ('parse','review'):
            for e in examples()[task+'_examples']:
                with self.subTest(case=e['id']):validate_output(task,e['expected_output'],e['input'])

    def test_parameter_and_relative_changes(self):
        s=self.session();o,c=self.response(s);s.apply(o,c)
        self.assertEqual(s.draft.plan.parameters.damage,'2d6')
        self.assertEqual(s.draft.plan.parameters.rarity,'Legendary')
        o,c=self.response(s,'E04');s.apply(o,c)
        self.assertEqual(s.draft.plan.parameters.weight_kg,0.25)
        with self.assertRaises(ValueError):s.apply(o,c)

    def test_state_is_not_lost_on_bad_output(self):
        s=self.session();o,c=self.response(s);old=digest(s.draft.plan)
        o['operations'][0]['payload']['value']='arbitrary code'
        with self.assertRaises(ValueError):s.apply(o,c)
        self.assertEqual(digest(s.draft.plan),old)

    def test_protocol_recovery_preserves_plan_and_deduplicates_request(self):
        from unittest.mock import patch
        from backend.task8_protocol import Task8Model
        s=self.session(); s.model=Task8Model()
        before=s.draft.plan.model_dump(mode='json')
        with patch.object(Task8Model,'parse',return_value=({},None)) as call:
            result=s.submit('伤害增加1，名字改成星夜匕首。','recovery_test')
            repeated=s.submit('伤害增加1，名字改成星夜匕首。','recovery_test')
        self.assertEqual(call.call_count,2)
        self.assertEqual(result,repeated)
        self.assertFalse(s.history[-1]['parsed'])
        self.assertEqual(s.draft.plan.parameters.model_dump(mode='json'),before['parameters'])
        self.assertEqual(s.draft.plan.display.model_dump(mode='json'),before['display'])
        self.assertEqual(s.draft.plan.effects,[])
        self.assertEqual(s.requirements[-1]['quote'],'伤害增加1，名字改成星夜匕首。')
        self.assertEqual(len(s.issues),1)
        with self.assertRaises(ValueError):s.preview()

    def test_unknown_text_owner_rejected_before_application(self):
        s=self.session();o,c=self.response(s,'E09')
        o['text_requests'][0]['target']['owner']=s.draft.plan.base_equipment
        old=digest(s.draft.plan)
        with self.assertRaisesRegex(ValueError,'unknown_text_owner'):s.apply(o,c)
        self.assertEqual(digest(s.draft.plan),old)

    def test_lookup_exhaustion_offers_choice_without_substitution(self):
        s=self.session();calls=[]
        example=next(e for e in examples()['parse_examples'] if e['id']=='E13')
        class MissingModel:
            def run(self,task,context):
                calls.append(context['capabilities']['lookup_state'])
                o=copy.deepcopy(example['expected_output']);o.update(context['request'])
                o['requirements'][0]['quote']=context['latest_message']['text']
                return o,None
        s.model=MissingModel()
        result=s.submit(example['input']['latest_message']['text'],'missing_resource')
        self.assertEqual(calls,['initial','expanded'])
        self.assertFalse(result['recovery']['automatic_substitution'])
        self.assertEqual(s.draft.plan.effects,[])
        self.assertTrue(s.issues)
        with self.assertRaises(ValueError):s.preview()

    def test_v2_routes_targeted_examples_within_budget(self):
        from backend.task8_protocol import select_examples
        for name in ['E09','E13']:
            e=next(e for e in examples()['parse_examples'] if e['id']==name)
            chosen=select_examples('parse',e['input'])
            self.assertIn(name,[x['id'] for x in chosen])
            self.assertLessEqual(len(chosen),3)

    def test_dependency_pair_commits_once(self):
        s=self.session('create_body_armor');o,c=self.response(s,'E11')
        before=s.draft.revision;result=s.apply(o,c)
        self.assertFalse(result['failed']);self.assertEqual(s.draft.revision,before+1)
        p=s.draft.plan;status=next(e for e in p.effects if e.kind=='independent_status')
        trigger=next(e for e in p.effects if e.kind=='trigger')
        self.assertEqual(trigger.status_draft_id,status.id);self.assertEqual(status.amount,0)
        files,_=render_plan(p.model_copy(update={'unresolved':[], 'display':p.display.model_copy(update={'name':'测试'})}),str(uuid.uuid4()),catalog=self.catalog,resources=self.resources)
        self.assertIn('AC(1)',str(files));self.assertNotIn('Ability(Strength,0)',str(files))

    def test_unknown_requirement_blocks_partial_success(self):
        s=self.session();o,c=self.response(s,'E08')
        c['capabilities']['checks'].append({'id':'check_growth_missing','result':'capability_gap'})
        s.apply(o,c)
        self.assertEqual(s.draft.plan.parameters.weight_kg,.5)
        self.assertTrue(s.draft.plan.unresolved)
        with self.assertRaises(ValueError):s.preview()

    def test_failed_group_does_not_erase_valid_group(self):
        s=self.session('create_body_armor');o,c=self.response(s)
        result=s.apply(o,c)
        self.assertTrue(result['failed']);self.assertIsNone(s.draft.plan.parameters.damage)
        self.assertEqual(s.draft.plan.parameters.weight_kg,.5)

    def test_full_current_effect_not_replaced_by_patch(self):
        s=self.session();p=s.draft.plan
        p.effects=Plan.model_validate(examples()['parse_examples'][4]['input']['current_plan']).effects
        s.draft=Draft(p);o,c=self.response(s,'E05');s.apply(o,c)
        self.assertEqual(len(s.draft.plan.effects),1)
        self.assertEqual(s.draft.plan.effects[0].event,'on_damaged')
        self.assertEqual(s.draft.plan.effects[0].dice,'1d6')

    def reviewed(self):
        s=self.session();p=s.draft.plan
        p.effects=Plan.model_validate(examples()['parse_examples'][8]['input']['current_plan']).effects
        s.draft=Draft(p);o,c=self.response(s,'E09');s.apply(o,c)
        c=s.review_context();t=c['texts'][0]
        raw={'schema_version':'review-v1',**c['request'],'plan_digest':c['plan_digest'],'items':[{
            'text_id':t['id'],'source_text_digest':t['source_text_digest'],'source_status':'conflict',
            'findings':[{'dimension':'condition','quote':'使用后永久','fact_refs':['effect_dex_bonus'],'explanation':'仅装备期间'}],
            'proposed_text':'装备期间，敏捷提高 2 点。','proposal_status':'consistent','proposal_findings':[]}]}
        s.apply_review(raw,c)
        self.assertTrue(s.texts)
        s.adopt_review(replacements=[t['id']])
        return s

    def test_review_receipt_actual_compilation_and_invalidation(self):
        s=self.reviewed();p=s.draft.plan
        self.assertFalse(validate_plan(p,self.catalog,self.resources,text_receipt=s.draft.text_receipt))
        with self.assertRaises(ValueError):render_plan(p,str(uuid.uuid4()),catalog=self.catalog,resources=self.resources)
        files,_=render_plan(p,str(uuid.uuid4()),catalog=self.catalog,resources=self.resources,text_receipt=s.draft.text_receipt)
        self.assertIn('装备期间，敏捷提高 2 点。','\n'.join(v.decode('utf-8') for v in files.values()))
        p.effects[0].amount=3
        self.assertTrue(validate_plan(p,self.catalog,self.resources,text_receipt=s.draft.text_receipt))
        forged=TextReceipt('x','fake','ai_reviewed')
        self.assertTrue(validate_plan(p,self.catalog,self.resources,text_receipt=forged))

    def test_review_no_missing_text_or_wrong_facts(self):
        e=copy.deepcopy(examples()['review_examples'][0]);e['expected_output']['items']=[]
        with self.assertRaises(ValueError):validate_output('review',e['expected_output'],e['input'])

    def test_model_prompt_budget_and_example_counts(self):
        s=self.session();c=s.context('重量减半','prompt')
        m=messages('parse',c)
        self.assertLessEqual(len(m),8)
        self.assertIn('parse-v1',m[0]['content'])

    def test_duplicate_keys_and_nonfinite_rejected(self):
        e=examples()['parse_examples'][0]
        for raw in ('{"x":1,"x":2}','{"x":NaN}'):
            with self.assertRaises(ValueError):validate_output('parse',raw,e['input'])

    def test_original_effect_restore_and_select_unknown(self):
        s=self.session();o,c=self.response(s)
        o['operations'][0].update(kind='select_reference',target='icon',payload={'reference_id':'invented'})
        result=s.apply(o,c);self.assertTrue(result['failed']);self.assertIsNone(s.draft.plan.icon)

    def test_snapshot_is_new_revision_and_restores_unresolved(self):
        s=self.session();o,c=self.response(s);s.apply(o,c)
        o,c=self.response(s,'E04');s.apply(o,c)
        c=s.context('撤销上次修改','undo')
        o={'schema_version':'parse-v1',**c['request'],'intent_summary':'恢复快照','requirements':[{
            'id':'r1','quote':'撤销上次修改','meaning':'恢复快照','operation_ids':['op1'],'issue_ids':[],
            'text_request_ids':[],'issue_update_ids':[],'no_change':False}],
            'operations':[{'id':'op1','requirement_ids':['r1'],'group_id':'g1','kind':'restore_snapshot','target':'draft',
                'payload':{'snapshot_id':'snapshot_2','evidence_quote':'撤销上次修改'}}],
            'issues':[],'issue_updates':[],'text_requests':[]}
        s.apply(o,c);self.assertEqual(s.draft.revision,4)
        self.assertEqual(s.draft.plan.parameters.weight_kg,.5);self.assertIsNone(s.draft.confirmation)

    def test_duplicate_request_does_not_apply_twice(self):
        s=self.session()
        class Fixture:
            calls=0
            def run(inner,task,c):
                inner.calls+=1
                o=copy.deepcopy(next(x for x in examples()['parse_examples'] if x['id']=='E04')['expected_output'])
                o.update(c['request']);return o,None
        s.model=Fixture();a=s.submit('重量减半。','same');b=s.submit('重量减半。','same')
        self.assertEqual(a,b);self.assertEqual(s.model.calls,1)
        with self.assertRaises(ValueError):s.submit('重量改成 3 千克','same')

    def test_conflicting_parameter_writes_block_group(self):
        s=self.session();o,c=self.response(s,'E04')
        extra=copy.deepcopy(o['operations'][0]);extra.update(id='op2',kind='set_parameter',payload={'value':2,'unit':'kg'})
        o['operations'].append(extra);o['requirements'][0]['operation_ids'].append('op2')
        result=s.apply(o,c);self.assertTrue(result['failed'])
        self.assertIsNone(s.draft.plan.parameters.weight_kg)

    def test_all_six_effect_types_adapt_into_B(self):
        for name in ('modify_existing','passive_copy'):
            s=self.session(name);base=self.cases[name]
            p=s.draft.plan;p.removed_original_passives=base['removed_original_passives'];s.draft=Draft(p)
            c=s.context('添加指定效果','all_effects_'+name,expanded=True)
            r={'id':'r1','quote':'添加指定效果','meaning':'添加指定效果','operation_ids':[],
               'issue_ids':[],'text_request_ids':[],'issue_update_ids':[],'no_change':False}
            o={'schema_version':'parse-v1',**c['request'],'intent_summary':'添加效果','requirements':[r],
               'operations':[],'issues':[],'issue_updates':[],'text_requests':[]}
            for i,e0 in enumerate(base['effects']):
                e=copy.deepcopy(e0);target=e.pop('id');e.pop('display',None)
                if e['kind']=='trigger' and e['action']!='status':e.pop('duration_turns')
                if e['kind']=='independent_status':
                    for b in e.get('bonuses',[]):b.pop('id',None);b.pop('display',None)
                for f in ('base_spell','base_status','base_passive','status_ref'):
                    if e.get(f):c['capabilities']['candidates'].append({'id':e[f]})
                op={'id':'op'+str(i),'requirement_ids':['r1'],'group_id':'all','kind':'add_effect','target':target,'payload':{'effect':e}}
                o['operations'].append(op);r['operation_ids'].append(op['id'])
            result=s.apply(o,c)
            self.assertFalse(result['failed'],result['failed'])
            self.assertEqual(len(s.draft.plan.effects),len(base['effects']))

    def test_spell_custom_text_applies_to_root_and_grant_not_all_children(self):
        from backend.text_review_v11 import issue_receipt
        p=Plan.model_validate(self.cases['status_spell_upcasts'])
        p.effects[0].display.description='测试已审核技能说明'
        receipt=issue_receipt(p,self.resources,path='ai_reviewed')
        files,_=render_plan(p,str(uuid.uuid4()),catalog=self.catalog,resources=self.resources,text_receipt=receipt)
        text='\n'.join(v.decode('utf-8') for v in files.values())
        self.assertIn('测试已审核技能说明',text)
        self.assertIn('消耗',text)

    def test_resource_change_invalidates_receipt(self):
        s=self.reviewed();changed=dict(self.resources,ruleset='changed')
        self.assertTrue(validate_plan(s.draft.plan,self.catalog,changed,text_receipt=s.draft.text_receipt))


if __name__=='__main__':unittest.main()
