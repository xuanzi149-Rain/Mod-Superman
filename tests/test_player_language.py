import copy
import unittest
from backend.crafting_v11 import Plan
from backend.task8 import Task8Session
from backend.task8_protocol import examples, messages, validate_output
from backend.player_language import player_issue, safe_text, TECHNICAL, policy
from backend.resource_names import name_score
from backend.ai_protocol import Interpretation
from scripts.crafting_compiler_v11 import load_resources
from scripts.equipment_catalog import load_catalog

class PlayerLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources=load_resources();cls.catalog=load_catalog()

    def session(self):
        return Task8Session(Plan(mode='modify_existing',base_equipment='equipment:8733edb7-f04e-4b6d-ad48-7d49fb782bef',user_goal='修改沉睡效果'),self.catalog,self.resources,inheritance='retain_base')

    def test_sussur_sleep_candidates_and_original_silence_are_distinct(self):
        s=self.session();c=s.context('把沉睡效果改为持续两回合','sleep')
        candidates={x['id']:x for x in c['capabilities']['candidates']}
        self.assertIn('SLEEPING',candidates)
        self.assertIn('沉睡',candidates['SLEEPING']['known_names'])
        self.assertEqual(candidates['SILENCED']['equipment_membership'],'inherited_reference')
        self.assertIn('ApplyStatus(SILENCED',c['native_equipment_fields']['WeaponFunctors'])
        self.assertEqual(s.draft.plan.effects,[])
        self.assertIn(policy(),messages('parse',c)[0]['content'])

    def test_fuzzy_names_are_candidates_only(self):
        self.assertGreater(name_score('治疗光辉','想要治疗光晖',True),0)
        self.assertEqual(name_score('治疗光辉','想要治疗光晖',False),0)
        self.assertEqual(name_score('沉默','沉睡',True),0)
        c=self.session().candidates('想要治疗光晖',expanded=True)
        self.assertTrue(any(x['id']=='Shout_HealingRadiance' for x in c))

    def test_id_question_triggers_one_lookup_and_preserves_requirement(self):
        s=self.session()
        class BadModel:
            calls=0
            def run(inner,task,c):
                inner.calls+=1
                o=copy.deepcopy(next(x for x in examples()['parse_examples'] if x['id']=='E13')['expected_output'])
                o.update(c['request']);o['requirements'][0]['quote']=c['latest_message']['text']
                o['issues'][0].update(kind='clarification',detail='需要具体状态ID',question='请提供沉睡的系统ID，例如 status:sleep_1_turn',options=[])
                return o,None
        s.model=BadModel();result=s.submit('修改沉睡效果','no-id')
        self.assertEqual(s.model.calls,2)
        self.assertTrue(s.issues);self.assertTrue(s.requirements)
        self.assertEqual(s.draft.plan.effects,[])
        for issue in s.issues.values():
            self.assertEqual(issue['kind'],'information_missing')
            self.assertIsNone(issue['question']);self.assertFalse(TECHNICAL.search(issue['detail']))
        self.assertFalse(result['recovery']['automatic_substitution'])

    def test_old_issue_cleanup_keeps_identity_and_requirements(self):
        old={'id':'old','requirement_ids':['r1'],'kind':'clarification','detail':'给出状态标识符','question':'输入UUID','options':['状态ID']}
        new=player_issue(old)
        self.assertEqual(new['id'],'old');self.assertEqual(new['requirement_ids'],['r1'])
        self.assertEqual(old['kind'],'clarification')
        self.assertIsNone(new['question'])
        naked={'detail':'请选择对应效果','question':'SLEEPING 还是 SLEEPING_MAGICAL？','options':[]}
        self.assertIsNone(player_issue(naked,['SLEEPING','SLEEPING_MAGICAL'])['question'])

    def test_legitimate_clarification_unchanged(self):
        question={'id':'q','kind':'clarification','detail':'需要明确持续时间','question':'持续几回合？','options':['一回合','两回合']}
        self.assertEqual(player_issue(question),question)
        self.assertEqual(safe_text('你想新增沉睡，还是修改沉默？'),'你想新增沉睡，还是修改沉默？')

    def test_known_references_translate_without_erasing_business_question(self):
        issue={'id':'q','kind':'clarification','detail':'原有效果是 SILENCED。',
               'question':'修改 SILENCED 还是新增 SLEEPING？','options':['SILENCED','SLEEPING']}
        out=player_issue(issue,['SILENCED','SLEEPING'],{'SILENCED':'沉默','SLEEPING':'沉睡'})
        self.assertEqual(out['kind'],'clarification')
        self.assertEqual(out['question'],'修改 沉默 还是新增 沉睡？')
        self.assertEqual(out['options'],['沉默','沉睡'])

    def test_structured_option_ids_are_not_player_id_requests(self):
        issue={'id':'q','kind':'clarification','detail':'原有效果是 SILENCED。',
               'question':'修改沉默，还是新增沉睡？',
               'options':[{'id':'opt_modify_silence','label':'修改 SILENCED'},
                          {'id':'opt_add_sleep','label':'新增沉睡'}]}
        result=player_issue(issue,['SILENCED'],{'SILENCED':'沉默'})
        self.assertEqual(result['kind'],'clarification')
        self.assertEqual(result['question'],issue['question'])
        self.assertEqual(result['options'][0],{'id':'opt_modify_silence','label':'修改 沉默'})

    def test_status_lookup_exposes_dependency_evidence_not_animation_test(self):
        c=self.session().context('命中施加一回合震慑','stun')
        refs={v['id'] for v in c['capabilities']['candidates']}
        self.assertIn('STUNNED',refs);self.assertNotIn('STUNNED_ANIMTEST',refs)
        evidence=[v for v in c['capabilities']['checks'] if v.get('resource_id')=='STUNNED']
        self.assertEqual(len(evidence),1);self.assertEqual(evidence[0]['result'],'capability_gap')

    def test_review_findings_do_not_request_technical_identifiers(self):
        e=copy.deepcopy(next(x for x in examples()['review_examples'] if any(i['findings'] for i in x['expected_output']['items'])))
        for i in e['expected_output']['items']:
            for f in i['findings']:f['explanation']='请提供状态ID'
        o=validate_output('review',e['expected_output'],e['input'])
        self.assertTrue(all(not TECHNICAL.search(f['explanation']) for i in o['items'] for f in i['findings']))

    def test_legacy_output_guard(self):
        o=Interpretation(result='clarify',operations=[],questions=['请提供UUID'],unsupported=[],explanation='需要状态ID')
        self.assertFalse(TECHNICAL.search(o.questions[0]));self.assertFalse(TECHNICAL.search(o.explanation))
