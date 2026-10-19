"""Local Chinese resource names for bounded candidate retrieval, not selection."""
from functools import lru_cache
from difflib import SequenceMatcher
import re
import xml.etree.ElementTree as ET
from scripts.generate_mod import ROOT

@lru_cache
def localization():
    return {(n.get('contentuid'),n.get('version')):''.join(n.itertext())
            for n in ET.parse(ROOT/'.tools/equipment-chinese.xml').getroot()}

def localized(fields, key):
    parts=fields.get(key,'').split(';')
    value=localization().get((parts[0],parts[1] if len(parts)>1 else '1'),'')
    return re.sub(r'<[^>]+>','',value)

def name_score(name, text, expanded):
    if len(name)<2:return 0
    if name.casefold() in text.casefold():return 1
    # Two-character effects such as 沉睡/沉默 must never fuzzy-match each other.
    if not expanded or len(name)<3 or len(name)>16:return 0
    for phrase in re.findall(r'[\u4e00-\u9fff]+',text):
        for width in (len(name)-1,len(name),len(name)+1):
            for start in range(max(0,len(phrase)-width+1)):
                part=phrase[start:start+width]
                if len(set(name)&set(part))>=2:
                    score=SequenceMatcher(None,name,part).ratio()
                    if score>=.75:return score
    return 0
