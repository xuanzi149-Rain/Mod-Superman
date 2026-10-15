from pathlib import Path
import xml.etree.ElementTree as E
import json, base64, copy

OUT=Path(__file__).resolve().parent
SRC=OUT.parent/'qa-v3'
SUP=SRC/'补充界面与状态'
NS='http://www.w3.org/2000/svg'
E.register_namespace('',NS)
def tag(e): return e.tag.split('}')[-1]
def load(path): return E.parse(path).getroot()
def remove(root,predicate):
    for parent in root.iter():
        for el in list(parent):
            if predicate(el): parent.remove(el)
logo=base64.b64encode((OUT.parent/'assets/bg3-logo-clear-transparent-2x.png').read_bytes()).decode()
def main_header(root,home=False):
    remove(root,lambda e:tag(e)=='text' and (''.join(e.itertext()) in ['使用指南','MAKE IT YOURS','博德之门3个性化Mod生成器','选好装备或技能，告诉我们你想怎么改。','先看清修改方案，再确认生成。'] or '设计预览' in ''.join(e.itertext())))
    if home:
        remove(root,lambda e:tag(e)=='circle' and e.attrib.get('cx')=='650')
        for e in root.iter():
            if tag(e)=='text' and '生成你的' in ''.join(e.itertext()): e.set('x','447.5');e.set('font-size','44');e.set('y','291')
            if tag(e)=='rect' and e.attrib.get('fill')=='#FFD600' and float(e.attrib.get('y','0'))<300: e.set('y','281')
    title=E.SubElement(root,'{'+NS+'}text',{'x':'720','y':'225' if home else '239','text-anchor':'middle','font-family':'Noto Sans SC','font-size':'28','font-weight':'500','fill':'#000000'});title.text='个性化Mod生成器'
    E.SubElement(root,'{'+NS+'}image',{'x':'637.5','y':'96','width':'165','height':'107.38','href':'data:image/png;base64,'+logo})
    return root

def serialize(root):
    texts=[];hotspots=[]
    for e in root.iter():
        if tag(e)=='g' and e.attrib.get('id','').startswith('button-'):
            r=next((a for a in e if tag(a)=='rect'),None);t=next((a for a in e if tag(a)=='title'),None)
            if r is not None and t is not None:hotspots.append({'label':t.text,'x':float(r.get('x')),'y':float(r.get('y')),'w':float(r.get('width')),'h':float(r.get('height'))})
        if tag(e)=='text':
            a=e.attrib;s=float(a.get('font-size','16'));texts.append({'text':''.join(e.itertext()),'x':float(a.get('x','0')),'y':float(a.get('y','0'))-s*1.08,'size':s,'weight':a.get('font-weight','400'),'color':a.get('fill','#000000'),'anchor':a.get('text-anchor','start')})
    images=[{'x':float(e.get('x','0')),'y':float(e.get('y','0')),'w':float(e.get('width')),'h':float(e.get('height'))} for e in root.iter() if tag(e)=='image']
    remove(root,lambda e:tag(e) in ['text','title','image'])
    return {'svg':E.tostring(root,encoding='unicode'),'texts':texts,'hotspots':hotspots,'images':images,'w':float(root.get('width')),'h':float(root.get('height'))}

boards=[]
def add(name,root,kind='page'):
    d=serialize(copy.deepcopy(root));d.update(name=name,kind=kind);boards.append(d)
main=[]
for i,f in enumerate(['01-问答首页','02-问答结果','03-确认后状态']):
    root=main_header(load(SRC/'字体修正版'/(f+'.svg')),i==0);main.append(root);add(f,root)
download=load(SUP/'04-结果下载页.svg');add('04-结果下载页',download)
# Retain consistent header on each full-page state.
header=E.Element('{'+NS+'}svg',{'width':'1440','height':'1000','viewBox':'0 0 1440 1000'})
for e in main[1]:
    a=e.attrib
    if tag(e)=='image' or (tag(e)=='text' and (''.join(e.itertext()) in ['MOD—SUPERMAN','＋ 新的修改','个性化Mod生成器'])) or (tag(e) in ['circle','polygon','rect','line'] and float(a.get('y',a.get('cy',a.get('y1','999'))))<90):header.append(copy.deepcopy(e))
for file in sorted(SUP.glob('状态-*.svg')):
    root=copy.deepcopy(header);g=E.SubElement(root,'{'+NS+'}g',{'transform':'translate(280 270)'})
    for e in load(file):g.append(copy.deepcopy(e))
    # Flatten translation to native coordinates for text and button metadata.
    for e in g.iter():
        for key in ['x','x1','x2','cx']:
            if key in e.attrib:e.set(key,str(float(e.get(key))+280))
        for key in ['y','y1','y2','cy']:
            if key in e.attrib:e.set(key,str(float(e.get(key))+270))
        if tag(e)=='polygon':e.set('points',' '.join(f'{float(p.split(",")[0])+280},{float(p.split(",")[1])+270}' for p in e.get('points').split()))
    g.attrib.pop('transform')
    add(file.stem.replace('状态-',''),root)
for file in sorted(SUP.glob('弹窗-*.svg')):add(file.stem,load(file),'overlay')
# Consistent parameter branches.
def replace(root,pairs):
    r=copy.deepcopy(root)
    for e in r.iter():
        if tag(e)=='text' and e.text:
            for a,b in pairs:e.text=e.text.replace(a,b)
    return r
add('03-确认3d6',replace(main[2],[('2d6','3d6'),('增加到2个','增加到3个'),('数量翻倍','数量改为3个')]))
add('04-结果3d6',replace(download,[('2d6','3d6'),('数量翻倍','数量改为3个')]))
add('03-生成3d6',replace(next(load(SUP/'状态-03-生成中.svg') for _ in [0]),[('2d6','3d6'),('数量翻倍','数量改为3个')]),'fragment')
# Skill home uses the approved home layout and substitutes the object/example.
add('01-治愈真言',replace(main[0],[('第一滴血短剑','治愈真言'),('装备','技能'),('把基础伤害骰数量翻倍，保留其他效果。','把施法距离改为36米，保留其他效果。')]))
add('04-技能下载',replace(download,[('第一滴血短剑','治愈真言'),('基础伤害','施法距离'),('1d6','18米'),('2d6','36米'),('数量翻倍','距离改为36米')]))
# Expand generated 3d6 state to a complete board.
d=boards[-3]
assert d['name']=='03-生成3d6'
r=copy.deepcopy(header)
for e in replace(load(SUP/'状态-03-生成中.svg'),[('2d6','3d6'),('数量翻倍','数量改为3个')]):
    for k in ['x','x1','x2','cx']:
        if k in e.attrib:e.set(k,str(float(e.get(k))+280))
    for k in ['y','y1','y2','cy']:
        if k in e.attrib:e.set(k,str(float(e.get(k))+270))
    if tag(e)=='polygon':e.set('points',' '.join(f'{float(p.split(",")[0])+280},{float(p.split(",")[1])+270}' for p in e.get('points').split()))
    r.append(e)
full=serialize(r);full.update(name=d['name'],kind='page');boards[-3]=full
for i,d in enumerate(boards): d['x']=(i%5)*1580;d['y']=(i//5)*1180
(OUT/'boards.json').write_text(json.dumps(boards,ensure_ascii=False),encoding='utf-8')
print('Prepared',len(boards),'boards')
