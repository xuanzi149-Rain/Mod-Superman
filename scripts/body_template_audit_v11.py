"""Audit complete equipment body maps and explicit native template behaviors."""
import hashlib,json
from pathlib import Path
import xml.etree.ElementTree as ET
from scripts.equipment_catalog import ROOT
ZERO='00000000-0000-0000-0000-000000000000'

def weapon_visual_issues(template, visuals, models, icons):
    """Use the complete B index, never the historical A eligibility verdict."""
    fields=template['effective']
    visual=visuals.get(fields.get('VisualTemplate',{}).get('value'),{})
    issues=[]
    if not icons.get(fields.get('Icon',{}).get('value'),{}).get('asset_exists'):
        issues.append('icon_atlas_not_verified')
    if not visual or visual.get('SourceFile','').casefold() not in models:
        issues.append('visual_model_not_verified')
    # Missing metadata is not evidence that skeleton remapping is unnecessary.
    if visual.get('SkeletonResource') or visual.get('NeedsSkeletonRemap')!='False':
        issues.append('skeleton_mapping_not_reviewed')
    return issues

def attrs(node):
    return {a.get('id'):a.get('value') for a in node.findall('attribute')}

def nodes_for(resources):
    nodes={}
    paths=sorted({p for t in resources['templates'].values() for p in t['direct_field_sources'].values()})
    # Explicit catalog source precedence, not filename sorting.
    order={'equipment-roots-Shared':0,'equipment-roots-Gustav':1,'equipment-roots-GustavX':2}
    paths.sort(key=lambda p:(next((v for k,v in order.items() if k in p),3),p))
    for path in paths:
        for n in ET.parse(ROOT/path).findall('.//node[@id="GameObjects"]'):
            a=attrs(n)
            if a.get('MapKey'):nodes[a['MapKey']]=n
    return nodes

def chain(key,nodes):
    result=[];seen=set()
    while key and key!=ZERO:
        if key in seen or key not in nodes:raise ValueError('template_missing_or_cyclic:'+key)
        seen.add(key);result.append(nodes[key]);key=attrs(nodes[key]).get('ParentTemplateId')
    return list(reversed(result))

def build(resources):
    inputs={}
    def fingerprint(p):
        inputs[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    races={};visuals={};tag_definitions={};action_resources={};level_maps={}
    for p in sorted((ROOT/'.tools/v11-body/Public').glob('*/Levelmaps/LevelMapValues.lsx')):
        fingerprint(p)
        for n in ET.parse(p).findall('.//node[@id="LevelMapSeries"]'):
            a=attrs(n);level_maps[a['Name']]=a
    for p in sorted((ROOT/'.tools/v11-tags').rglob('*.lsx')):
        fingerprint(p)
        n=ET.parse(p).find('.//node[@id="Tags"]')
        if n is not None:
            a=attrs(n)
            a['story']=any(x.get('value')=='Story' for x in n.findall('.//attribute[@id="Name"]')) or a.get('Name','').startswith('ORI_')
            tag_definitions[a['UUID']]=a
    for p in sorted((ROOT/'.tools/v11-body/Public').glob('*/ActionResource*Definitions/*.lsx')):
        fingerprint(p)
        for n in ET.parse(p).iter('node'):
            a=attrs(n)
            if a.get('Name') and a.get('UUID'):
                action_resources[a['Name']]=a
    for p in sorted((ROOT/'.tools/v11-body').rglob('EquipmentRaces.lsx')):
        fingerprint(p)
        for n in ET.parse(p).findall('.//node[@id="EquipmentRace"]'):
            a=attrs(n);races[a['Guid']]=a
    for p in sorted((ROOT/'.tools/v11-body/Public').rglob('_merged.lsx')):
        fingerprint(p)
        # Stream major resource nodes, keeping only ID/model metadata.
        for event,n in ET.iterparse(p,events=('end',)):
            if n.tag=='node' and n.get('id') in ('Resource','VisualBank'):
                a=attrs(n)
                if a.get('ID') and a.get('SourceFile'):visuals[a['ID']]={'source':str(p.relative_to(ROOT)),**a}
                n.clear()
    listing=ROOT/'build/v1.1/all-models.log';fingerprint(listing)
    models={line.split('\t')[0].casefold() for line in listing.read_text(encoding='utf-8-sig').splitlines()}
    nodes=nodes_for(resources);results={}
    for key,t in resources['templates'].items():
        reasons=[];mapping={};parents={};actions=[];tags=set();equipment=False
        try:ancestry=chain(key,nodes)
        except ValueError as e:
            results[key]={'qualified':False,'issues':[str(e)]};continue
        for n in ancestry:
            for child in n.findall('./children/node'):
                ident=child.get('id')
                if not child.findall('.//attribute'):
                    continue
                if ident=='Equipment':
                    equipment=True
                    for obj in child.findall('./children/node[@id="Visuals"]/children/node'):
                        a=attrs(obj);mapping[a['MapKey']]=[a.get('value') for a in obj.findall('./children/node[@id="MapValue"]/attribute[@id="Object"]')]
                    for obj in child.findall('./children/node[@id="ParentRace"]/children/node'):
                        a=attrs(obj);parents[a['MapKey']]=a['MapValue']
                elif ident=='Tags':tags.update(a.get('value') for a in child.findall('.//attribute[@id="Object"]'))
                elif ident.endswith('Actions'):
                    for action in child.findall('./children/node[@id="Action"]'):
                        a=attrs(action);detail=action.find('./children/node[@id="Attributes"]');v=attrs(detail) if detail is not None else {}
                        if a.get('ActionType')=='26' and set(v)<= {'ActivateSoundEvent','Animation','PlayOnHUD','Conditions'} and not v.get('Conditions'):continue
                        if a.get('ActionType')=='7' and v.get('StatsId')=='ORI_GALE_AVATAR_CONSUMEITEM' and v.get('Conditions')=="Tagged('REALLY_GALE', context.Source) and not Tagged('ORI_GALE_DONEWITHITEMS', context.Source)" and v.get('Consume')=='True':
                            actions.append({'event':ident,'kind':'gale_consumption','status':v['StatsId'],'description':'盖尔可吞噬此装备；会消耗物品。'})
                        else:reasons.append('unreviewed_template_action:'+ident+':'+str(a.get('ActionType')))
                elif ident=='InventoryList':
                    if any(a.get('value')!='Empty' for a in child.findall('.//attribute[@id="Object"]')):reasons.append('nonempty_template_inventory')
                elif ident not in ('Bounds','GameMaster'):
                    reasons.append('unreviewed_template_child:'+str(ident))
        for tag in sorted(tags):
            if tag not in tag_definitions:
                reasons.append('missing_tag_definition:'+tag)
            elif tag_definitions[tag]['story']:
                actions.append({'kind':'story_tag','tag':tag,'name':tag_definitions[tag]['Name'],'description':tag_definitions[tag].get('Description','')})
        body={}
        if equipment:
            for race,definition in races.items():
                current=race;seen=set();route=[]
                while current and current!=ZERO and current not in mapping:
                    if current in seen:reasons.append('body_fallback_cycle:'+race);break
                    seen.add(current);route.append(current)
                    current=parents.get(current,races.get(current,{}).get('DefaultParent'))
                refs=mapping.get(current,[])
                failures=[ref for ref in refs if ref not in visuals or visuals[ref]['SourceFile'].casefold() not in models]
                body[race]={'name':definition['Name'],'resolved_race':current,'fallback_chain':route,'visuals':refs,'missing_models':failures}
                if not refs:reasons.append('body_mapping_missing:'+race)
                elif failures:reasons.append('body_model_missing:'+race)
            for race in mapping:
                if race not in races:reasons.append('unknown_body_race:'+race)
        is_armor=resources['records'][t['stats']]['type']=='Armor'
        if is_armor:
            fields=resources['records'][t['stats']]['effective']
            rigid_or_invisible=fields.get('Shield')=='Yes' or fields.get('Slot') in ('Ring','Amulet')
            if not equipment and not rigid_or_invisible:reasons.append('armor_equipment_mapping_missing')
            icon=t['effective'].get('Icon',{}).get('value')
            if not resources['icon_asset_validation'].get(icon,{}).get('asset_exists'):reasons.append('icon_unverified')
            ground=t['effective'].get('VisualTemplate',{}).get('value')
            if ground not in visuals or visuals[ground]['SourceFile'].casefold() not in models:reasons.append('ground_visual_missing')
            if fields.get('Shield')=='Yes' and ground in visuals and (visuals[ground].get('NeedsSkeletonRemap')=='True' or visuals[ground].get('SkeletonResource')):
                reasons.append('shield_skeleton_mapping_required')
        else:reasons.extend(weapon_visual_issues(t,visuals,models,resources['icon_asset_validation']))
        results[key]={'qualified':not reasons,'issues':sorted(set(reasons)),'body_mapping':body,'special_actions':actions,'inherited_tags':sorted(tags),'policy':'inherit_complete_native_template; explicit acknowledgement for reviewed story actions'}
    return {'schema_version':'body-template-audit-2','inputs_sha256':inputs,'races':races,'visuals':visuals,'templates':results,'tags':tag_definitions,'action_resources':action_resources,'level_maps':level_maps}

if __name__=='__main__':
    r=json.loads((ROOT/'build/v1.1/resource-catalog.json').read_text(encoding='utf-8'))
    result=build(r);(ROOT/'build/v1.1/body-template-audit.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print('visuals',len(result['visuals']),'races',len(result['races']))
    from collections import Counter
    print(Counter('qualified' if v['qualified'] else v['issues'][0].split(':')[0] for v in result['templates'].values()))
    print('breastplate',result['templates']['4814825e-23ee-41ed-9784-d9963434150d']['issues'])
