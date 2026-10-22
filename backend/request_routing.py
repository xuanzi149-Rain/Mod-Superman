"""Conservative local routing: unknown/mixed input always uses the full parser."""
import re


def simple_parameter_request(context):
    if context['latest_message'].get('answers_issue_ids') or context.get('intent_state',{}).get('open_issues'):
        return False
    text=context['latest_message']['text'].strip().rstrip('。.!！')
    patterns=[r'(?:名字|名称)(?:改为|改成|设为)\s*[A-Za-z0-9_\-]{1,60}',
              r'重量(?:改为|改成|设为)\s*\d+(?:\.\d+)?\s*(?:kg|千克|公斤)?',
              r'稀有度(?:改为|改成|设为)\s*(?:普通|精良|稀有|珍奇|传说)']
    parts=re.split(r'[，,；;]',text)
    return bool(parts) and all(any(re.fullmatch(p,part.strip()) for p in patterns) for part in parts)


def catalog_answer(text, plan, catalog):
    # Full matches deliberately exclude combined questions and modification commands.
    if not re.fullmatch(r'(?:请问|这个装备|这件装备|当前装备)?\s*(?:可以|能|支持)(?:修改|改)(?:哪些|什么)参数[？?。\s]*',text.strip()):
        return None
    from backend.crafting_v11 import BaseParameters
    labels={'weight_kg':'重量','rarity':'稀有度','value':'价值','weapon_properties':'武器属性',
            'damage':'伤害骰','versatile_damage':'两用武器的双手伤害骰','damage_type':'伤害类型',
            'enchantment':'附魔等级','armor_class':'护甲等级','dexterity_rule':'敏捷护甲规则'}
    category=catalog['items'][plan.base_equipment].get('category')
    fields=['weight_kg','rarity','value']
    if category=='weapon':fields+=['damage','damage_type','enchantment','weapon_properties','versatile_damage']
    elif category in ('body','shield','clothing'):fields+=['armor_class']+(['dexterity_rule'] if category!='shield' else [])
    fields=[f for f in fields if f in BaseParameters.model_fields]
    return ('当前装备可设置名称、展示说明，以及'+ '、'.join(labels[f] for f in fields)+
            '。也可以描述希望添加或修改的独立效果。具体取值、装备适用性及资源依赖仍需程序校验；'+
            '近战、远程、投掷等结构属性目前不能仅通过改属性列表切换。此回答依据当前支持目录，尚未修改方案。')
