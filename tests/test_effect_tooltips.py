import json
import unittest
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from backend.crafting_v11 import Plan, Draft, digest
from backend.text_review_v11 import issue_receipt
from scripts.crafting_compiler_v11 import load_resources, render_plan, generate_draft, FIRST_BLOOD, check_files
from scripts.equipment_catalog import load_catalog, parse_stats
from scripts.generate_mod import ROOT

class EffectTooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=load_resources();cls.c=load_catalog()
    def plan(self,display=None):
        return Plan(mode='modify_existing',base_equipment=FIRST_BLOOD,user_goal='合成词条回归',effects=[dict(kind='trigger',id='heal',event='on_hit',condition='always',target='self',action='heal',dice='1d6',duration_turns=1,display=display or {})])
    def render(self,p):
        receipt=issue_receipt(p,self.r,path='ai_reviewed') if p.effects[0].display.description else None
        files,m=render_plan(p,'ba8908da-5806-4eed-a55e-d098142c21ba',catalog=self.c,resources=self.r,text_receipt=receipt)
        check_files(files,m,self.r)
        entries={x.name:x for path,b in files.items() if path.parent.name=='Data' for x in parse_stats(b.decode(),str(path))}
        texts={x.get('contentuid'):x.text or '' for path,b in files.items() if path.suffix=='.xml' for x in ET.fromstring(b).findall('content')}
        return entries[m['effect_ids']['heal']].fields,texts
    def test_blank_hides_tooltip_not_healing(self):
        fields,texts=self.render(self.plan())
        self.assertIn('IsHidden',fields['Properties'].split(';'))
        self.assertEqual(fields['StatsFunctors'],'RegainHitPoints(SELF,1d6)')
        self.assertEqual(texts[fields['Description'].split(';')[0]],'')
    def test_written_tooltip_keeps_exact_text_and_mechanics(self):
        p=self.plan({'name':'回春','description':'使用此武器命中后，为自己恢复1d6生命值。'})
        fields,texts=self.render(p)
        self.assertNotIn('IsHidden',fields['Properties'].split(';'))
        self.assertEqual(texts[fields['Description'].split(';')[0]],p.effects[0].display.description)
        self.assertEqual(fields['StatsFunctors'],'RegainHitPoints(SELF,1d6)')
    def test_name_only_has_resolved_empty_description(self):
        fields,texts=self.render(self.plan({'name':'回春'}))
        self.assertNotIn('IsHidden',fields['Properties'].split(';'))
        self.assertEqual(texts[fields['Description'].split(';')[0]],'')
    def test_custom_text_needs_no_semantic_review(self):
        render_plan(self.plan({'description':'恢复999生命'}),str(uuid.uuid4()),catalog=self.c,resources=self.r)
    def test_real_packages_preserve_documented_xml_loader_path(self):
        results=[]
        for display in ({},{'name':'回春','description':'使用此武器命中后，为自己恢复1d6生命值。'}):
            p=self.plan(display);d=Draft(p)
            # Synthetic expected text is known and checked above; no model call.
            receipt=issue_receipt(p,self.r,path='ai_reviewed') if display else None
            self.assertEqual(d.review(self.c,self.r,text_receipt=receipt),[])
            d.confirm(expected_revision=1,expected_digest=digest(p))
            pak=generate_draft(d,str(uuid.uuid4()),ROOT/'build/tooltip-regression',catalog=self.c,resources=self.r)
            extracted=pak.parent/'unpacked'
            xml=list(extracted.glob('Mods/*/Localization/Chinese/chinese.xml'))
            self.assertEqual(len(xml),1)
            self.assertFalse(list(extracted.rglob('*.loca')))
            texts={e.get('contentuid'):e.text or '' for e in ET.parse(xml[0]).findall('content')}
            passive=list(extracted.glob('Public/*/Stats/Generated/Data/PassiveData.txt'))[0]
            for entry in parse_stats(passive.read_text(encoding='utf-8'),str(passive)):
                for field in ('DisplayName','Description'):self.assertIn(entry.fields[field].split(';')[0],texts)
                self.assertEqual('IsHidden' in entry.fields['Properties'].split(';'),not bool(display))
            results.append({'pak':str(pak),'custom_text':bool(display),'package_check':'passed','game_validation':'not_performed'})
        (ROOT/'docs/v1.1/词条修复打包检查.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':unittest.main()
