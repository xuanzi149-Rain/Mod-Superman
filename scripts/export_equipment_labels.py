"""Build player-facing duplicate-name labels from the local resource snapshot."""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_labels(catalog, resources):
    groups = defaultdict(list)
    for ident, item in catalog['items'].items():
        groups[(' '.join(item['display_name'].split()), item['category'])].append(ident)
    result = {}
    for (name, category), ids in groups.items():
        if len(ids) < 2:
            continue
        ids.sort()
        properties, visuals = {}, {}
        for ident in ids:
            template = resources['templates'][ident.removeprefix('equipment:')]
            fields = resources['records'][template['stats']]['effective']
            boosts = fields.get('DefaultBoosts', '')
            enchantment = re.search(r'(?:^|;)WeaponEnchantment\((\d+)\)', boosts)
            values = {}
            if category == 'weapon':
                values['enchantment'] = '附魔 +' + enchantment[1] if enchantment else '无附魔加值'
            for key, title, suffix in [('Damage', '伤害 ', ''), ('ArmorClass', '护甲等级 ', ''), ('Weight', '重量 ', ' kg')]:
                value = fields.get(key, '')
                if re.fullmatch(r'\d+(?:\.\d+)?|\d+d\d+(?:[+-]\d+)?', value):
                    values[key] = title + value + suffix
            rarity = {'Common': '普通', 'Uncommon': '精良', 'Rare': '珍奇', 'VeryRare': '极珍奇', 'Legendary': '传说'}.get(fields.get('Rarity'))
            if rarity:
                values['rarity'] = rarity
            properties[ident] = values
            visuals[ident] = template['effective'].get('VisualTemplate', {}).get('value')
        keys = ['enchantment', 'Damage', 'ArmorClass', 'rarity', 'Weight']
        different = [key for key in keys if len({properties[i].get(key) for i in ids}) > 1]
        labels = {i: [properties[i][k] for k in different if k in properties[i]] for i in ids}
        # Only add appearance numbers where the property labels still collide.
        collisions = defaultdict(list)
        for ident in ids:
            collisions[tuple(labels[ident])].append(ident)
        for matching in collisions.values():
            appearances = sorted({visuals[i] for i in matching if visuals[i]})
            if len(appearances) > 1:
                for ident in matching:
                    if visuals[ident]:
                        labels[ident].append('外观 ' + str(appearances.index(visuals[ident]) + 1))
        collisions = defaultdict(list)
        for ident in ids:
            collisions[tuple(labels[ident])].append(ident)
        for matching in collisions.values():
            if len(matching) > 1:
                for number, ident in enumerate(matching, 1):
                    labels[ident].append('版本 ' + str(number))
        for ident in ids:
            result[ident] = {'name': name, 'category': category, 'detail': '，'.join(labels[ident])}
        assert len({result[i]['detail'] for i in ids}) == len(ids)
    return result


if __name__ == '__main__':
    catalog = json.loads((ROOT / 'data/equipment_catalog.json').read_text(encoding='utf-8'))
    resources = json.loads((ROOT / 'build/v1.1/resource-catalog.json').read_text(encoding='utf-8'))
    labels = build_labels(catalog, resources)
    (ROOT / 'web/equipment-labels.json').write_text(json.dumps(labels, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Exported {len(labels)} duplicate-name labels.')
