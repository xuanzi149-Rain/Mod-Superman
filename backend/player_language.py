"""Player-facing language boundary; resource identifiers remain internal."""
import copy
import re
from functools import lru_cache
from scripts.generate_mod import ROOT

TECHNICAL = re.compile(r'(?<![A-Za-z])(?:id|uuid|guid)(?![A-Za-z])|标识符|(?:系统|技术|状态|资源)标识|内部编号|Stats\s*名称|base_(?:spell|passive|status)|(?:status|spell|passive|equipment):[a-z0-9_-]+', re.I)
REPHRASE = '请用效果名称或实际表现说明你想修改什么；有相似效果时，请描述触发条件、作用对象及它们的区别。'
MISSING = '这项要求仍待确认，系统需要进一步匹配对应效果。请描述希望发生的效果、作用对象和触发条件；原需求会保留，不会自动替换成其他效果。'
IMPLEMENTATION = re.compile(r'JSON|schema|relative_parameter|set_parameter|versatile_damage|(?<![A-Za-z_])damage(?![A-Za-z_])|协议|非法格式', re.I)

@lru_cache
def policy():
    return (ROOT/'prompts/player-language.md').read_text(encoding='utf-8')

def safe_text(text, fallback=REPHRASE):
    return fallback if isinstance(text,str) and TECHNICAL.search(text) else text

def player_issue(issue, internal_ids=(), names=None):
    result=copy.deepcopy(issue)
    if 'check_ally_aura_missing' in result.get('evidence_refs',[]):
        result['detail']='这项要求已理解，但当前尚未实现“装备后自动影响周围队友”的持续光环生成能力。距离、队友范围和伤害加成都已保留；不会替换成佩戴者命中效果。'
        result['question']=None
    if isinstance(result.get('question'),str):
        result['question']=result['question'].replace('请点击“补充说明”重试这项要求','请在上方输入框补充或重试这项要求')
    detail=str(result.get('detail') or '')
    if re.search(r'validation error|errors\.pydantic\.dev|input_type=|input_value=',detail,re.I):
        result['detail']='系统生成的效果参数没有通过检查，本次效果未应用；你的原要求和补充说明已保留。'
        result['question']='请保留这项要求等待修正，或明确选择其他效果；无需提供程序字段或重新填写已说明的条件。'
        return result
    # A real internal reference in an explanation is not a request for the player
    # to supply it. Translate known references before deciding to replace a question.
    def readable(value):
        if not isinstance(value,str):return value
        for ref,name in sorted((names or {}).items(),key=lambda item:-len(item[0])):
            value=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(ref)+r'(?![A-Za-z0-9_])',lambda _:name,value)
        return value
    for field in ('detail','question'):result[field]=readable(result.get(field))
    # Explanations about serialization are not missing game resources. Remove
    # those sentences without losing a valid question or its readable choices.
    detail=result.get('detail')
    if isinstance(detail,str) and IMPLEMENTATION.search(detail):
        sentences=re.findall(r'[^。！？\n]+[。！？\n]?',detail)
        result['detail']=''.join(s for s in sentences if not IMPLEMENTATION.search(s)).strip() or '需要确认这项修改的具体含义，原需求已保留。'
    result['options']=[{**v,'label':readable(v['label'])} if isinstance(v,dict) else readable(v)
                       for v in result.get('options',[])]
    # Option IDs are protocol bookkeeping, never player-visible text. Inspecting
    # str(option) would mistake every {'id': ...} for a request to supply an ID.
    fields=[result.get('detail',''),result.get('question',''),
            *(v.get('label','') if isinstance(v,dict) else v for v in result['options'])]
    leaked=any(re.search(r'(?<![A-Za-z0-9_])'+re.escape(ref)+r'(?![A-Za-z0-9_])',str(v))
               for ref in internal_ids if len(ref)>3 for v in fields if v)
    if leaked or any(TECHNICAL.search(str(v)) for v in fields if v):
        # Keep the issue and its requirement references. The usual bounded lookup
        # path runs before asking the player for a description, never an identifier.
        result.update(kind='information_missing',detail=MISSING,question=None,options=[],evidence_refs=[])
    return result

def player_output(task, output, context):
    result=copy.deepcopy(output)
    if task=='parse':
        identifiers=[v['id'] for v in context['capabilities']['candidates']]
        names={v['id']:v['name'] for v in context['capabilities']['candidates'] if v.get('name') and v['name']!=v['id']}
        result['issues']=[player_issue(i,identifiers,names) for i in result['issues']]
        result['intent_summary']=safe_text(result['intent_summary'],'已保留你的要求，将根据效果描述核对修改目标。')
    else:
        for item in result['items']:
            for finding in item['findings']+item['proposal_findings']:
                finding['explanation']=safe_text(finding['explanation'],MISSING)
    return result
