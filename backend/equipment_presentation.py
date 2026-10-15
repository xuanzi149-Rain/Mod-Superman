"""Curated acquisition evidence; independent of generated-package game validation."""
import json
from scripts.generate_mod import ROOT

PRESENTATIONS = json.loads((ROOT / 'data/equipment_presentation.json').read_text(encoding='utf-8'))['items']


def presentation(item):
    evidence = PRESENTATIONS.get(item['root_uuid'])
    # A similar name or shared Stats record alone does not establish acquisition.
    if evidence and evidence['record'] == item['record']:
        return {k: v for k, v in evidence.items() if k != 'record'}
    return {'availability': 'unverified', 'kind': '待核实候选',
            'effect': '', 'location': '尚未核实正式游戏中的获取方式'}
