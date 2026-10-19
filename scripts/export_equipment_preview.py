"""Export read-only original equipment previews from the audited local snapshot."""
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_previews(catalog, resources, texts):
    def localized(value):
        if isinstance(value, dict):
            key = (value.get('handle'), value.get('version', '1'))
        else:
            parts = (value or '').split(';')
            key = (parts[0], parts[1] if len(parts) > 1 else '1')
        return html.unescape(re.sub(r'<[^>]*>', '', texts.get(key, ''))).strip()

    result = {}
    for ident, item in catalog['items'].items():
        template = resources['templates'][ident.removeprefix('equipment:')]
        fields = resources['records'][template['stats']]['effective']
        attrs = []
        for key, label in [('Damage', '基础伤害'), ('VersatileDamage', '双手伤害'), ('ArmorClass', '护甲等级'), ('Weight', '重量（kg）')]:
            value = fields.get(key, '')
            if re.fullmatch(r'\d+(?:\.\d+)?|\d+d\d+(?:[+-]\d+)?', value):
                attrs.append([label, value])
        rarity = {'Common': '普通', 'Uncommon': '精良', 'Rare': '珍奇', 'VeryRare': '极珍奇', 'Legendary': '传说'}.get(fields.get('Rarity'))
        if rarity:
            attrs.append(['稀有度', rarity])
        boosts = fields.get('DefaultBoosts', '')
        enchantment = re.search(r'(?:^|;)WeaponEnchantment\((\d+)\)', boosts)
        if item['category'] == 'weapon':
            attrs.append(['武器附魔', '+' + enchantment[1] if enchantment else '无附魔加值'])
        damage_types = {'Slashing': '挥砍', 'Piercing': '穿刺', 'Bludgeoning': '钝击', 'Fire': '火焰', 'Cold': '寒冷', 'Lightning': '闪电', 'Thunder': '雷鸣', 'Force': '力场', 'Psychic': '心灵', 'Poison': '毒素', 'Acid': '强酸', 'Radiant': '光耀', 'Necrotic': '黯蚀'}
        if fields.get('Damage Type') in damage_types:
            attrs.append(['伤害类型', damage_types[fields['Damage Type']]])
        property_names = {'Thrown': '投掷', 'Melee': '近战', 'Ranged': '远程', 'Dippable': '可蘸取', 'Versatile': '两用', 'Magical': '魔法', 'Finesse': '灵巧', 'Light': '轻型', 'Heavy': '重型', 'Reach': '长柄', 'Twohanded': '双手'}
        properties = [property_names[v] for v in fields.get('Weapon Properties', '').split(';') if v in property_names]
        if properties:
            attrs.append(['武器特性', '、'.join(properties)])
        effects, unresolved = [], 0
        refs = [x for x in fields.get('PassivesOnEquip', '').split(';') if x]
        refs += re.findall(r'UnlockSpell\(([^,;)]+)', ';'.join(fields.get(k, '') for k in fields if 'Boosts' in k))
        for ref in dict.fromkeys(refs):
            effect = resources['records'].get(ref, {}).get('effective', {})
            name = localized(effect.get('DisplayName'))
            description = localized(effect.get('Description'))
            # Dynamic game expressions are not executed or presented as resolved values.
            if re.search(r'\[\d+\]', description):
                description = re.sub(r'\[\d+\]', '（动态数值）', description)
            if name or description:
                effects.append({'name': name or '原生效果', 'description': description})
            else:
                unresolved += 1
        result[ident] = {
            'name': item['display_name'], 'attributes': attrs,
            'description': localized(template['effective'].get('Description')),
            'effects': effects, 'unresolved': unresolved,
            'note': '依据本地原版资源展示；动态数值未展开，隐藏机制及难度差异可能未完整展示。',
        }
    return result


if __name__ == '__main__':
    catalog = json.loads((ROOT / 'data/equipment_catalog.json').read_text(encoding='utf-8'))
    resources = json.loads((ROOT / 'build/v1.1/resource-catalog.json').read_text(encoding='utf-8'))
    texts = {(n.get('contentuid'), n.get('version')): ''.join(n.itertext()) for n in ET.parse(ROOT / '.tools/equipment-chinese.xml').getroot()}
    previews = build_previews(catalog, resources, texts)
    (ROOT / 'web/equipment-previews.json').write_text(json.dumps(previews, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(f'Exported {len(previews)} original equipment previews.')
