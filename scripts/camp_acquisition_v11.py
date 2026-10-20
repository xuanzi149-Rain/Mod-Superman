"""Native OneTimeRewards delivery; no chapter checks or runtime scripts."""
import uuid
import xml.etree.ElementTree as ET

ENTRY = {'id':'camp_chest','name':'营地 · 个人宝箱',
         'mechanism':'OneTimeRewards','limitations':['启用 Mod 并加载存档后，返回营地查看个人宝箱。',
         '同一奖励标识按存档一次性发放，重新加载不应反复补发。',
         '不设章节条件；各章节和已有存档实际到账尚待游戏验证。']}

def reward_id(module_id):
    return str(uuid.uuid5(uuid.UUID(module_id),'camp_chest_reward'))

def rewards_xml(module_id, template_id):
    root=ET.Element('save')
    ET.SubElement(root,'version',major='4',minor='8',revision='0',build='500')
    region=ET.SubElement(root,'region',id='OneTimeRewards')
    node=ET.SubElement(ET.SubElement(ET.SubElement(region,'node',id='root'),'children'),'node',id='OneTimeReward')
    for key,kind,value in [('Amount','uint32','1'),('ItemTemplateId','FixedString',template_id),('UUID','guid',reward_id(module_id))]:
        ET.SubElement(node,'attribute',id=key,type=kind,value=value)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)

def check_rewards(data,module_id,template_id,*,binary_roundtrip=False):
    root=ET.fromstring(data)
    if binary_roundtrip and root.find('./region[@id="root"]') is not None:
        root.find('./region[@id="root"]').set('id','OneTimeRewards')
    rewards=root.findall('./region[@id="OneTimeRewards"]/node[@id="root"]/children/node[@id="OneTimeReward"]')
    if len(rewards)!=1:raise ValueError('Expected one camp chest reward')
    attrs={a.get('id'):(a.get('type'),a.get('value')) for a in rewards[0].findall('attribute')}
    if attrs!={'Amount':('uint32','1'),'ItemTemplateId':('FixedString',template_id),'UUID':('guid',reward_id(module_id))}:
        raise ValueError('Camp reward/template mismatch')
