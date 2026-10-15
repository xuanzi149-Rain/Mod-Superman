from pathlib import Path
import base64, html, json, math, zipfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / '补充界面与状态'
OUT.mkdir(exist_ok=True)
WHITE, BLACK, RED, YELLOW = '#FFFFFF', '#000000', '#D71920', '#FFD600'
inventory = []

class Canvas:
    def __init__(self, w=880, h=590):
        self.w, self.h = w, h
        self.image = Image.new('RGB', (w*2, h*2), WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self.svg = []
        self.labels = []
        self.rect(0, 0, w, h)
    def rect(self,x,y,w,h,fill=WHITE,r=0,stroke=None):
        self.draw.rounded_rectangle((x*2,y*2,(x+w)*2,(y+h)*2),r*2,fill=fill,outline=stroke,width=2)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"'+(f' stroke="{stroke}"' if stroke else '')+'/>')
    def circle(self,x,y,r,fill=WHITE,stroke=None):
        self.draw.ellipse(((x-r)*2,(y-r)*2,(x+r)*2,(y+r)*2),fill=fill,outline=stroke,width=2)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"'+(f' stroke="{stroke}"' if stroke else '')+'/>')
    def line(self,x,y,x2,y2):
        self.draw.line((x*2,y*2,x2*2,y2*2),fill=BLACK,width=2)
        self.svg.append(f'<line x1="{x}" y1="{y}" x2="{x2}" y2="{y2}" stroke="{BLACK}"/>')
    def text(self,x,y,s,size=16,color=BLACK,strong=False,center=False):
        font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc' if strong else 'C:/Windows/Fonts/msyh.ttc',size*2)
        width=self.draw.textlength(s,font=font)/2
        if center:x-=width/2
        assert x>=0 and x+width<=self.w and y+size*1.5<=self.h,(s,x,y,width,self.w)
        self.draw.text((x*2,y*2),s,font=font,fill=color,anchor='lt')
        self.svg.append(f'<text x="{x:.2f}" y="{y+size}" font-family="Noto Sans SC" font-size="{size}" font-weight="{500 if strong else 400}" fill="{color}">{html.escape(s)}</text>')
        self.labels.append(s)
    def button(self,x,y,w,label,primary=True):
        self.svg.append(f'<g id="button-{len(self.labels)}"><title>{html.escape(label)}</title>')
        self.rect(x,y,w,48,RED if primary else WHITE,24,None if primary else BLACK)
        self.text(x+w/2,y+14,label,14,WHITE if primary else BLACK,True,True)
        self.svg.append('</g>')
    def chip(self,x,y,w,label,selected=False):
        self.rect(x,y,w,36,YELLOW if selected else WHITE,18,None if selected else BLACK)
        self.text(x+w/2,y+10,label,12,center=True)
    def avatar(self,x,y):
        self.circle(x,y,18,YELLOW)
        self.star(x,y,11,BLACK)
    def star(self,x,y,r,color):
        pts=[]
        for i in range(16):
            a=i*math.pi/8-math.pi/2
            rr=r if i%2==0 else r*.48
            pts.append((x+math.cos(a)*rr,y+math.sin(a)*rr))
        self.draw.polygon([(a*2,b*2) for a,b in pts],fill=color)
        self.svg.append('<polygon points="'+' '.join(f'{a:.2f},{b:.2f}' for a,b in pts)+f'" fill="{color}"/>')
    def question(self,label='把基础伤害骰数量翻倍，保留其他效果。'):
        self.rect(268,12,612,64,BLACK,24)
        self.text(292,33,label,16,WHITE)
    def answer(self,title):
        self.avatar(18,118)
        self.text(52,102,title,22,strong=True)
    def composer(self,y=468,prompt='需要调整哪里？继续告诉我们。',enabled=True):
        self.rect(0,y,880,112,WHITE,26,BLACK)
        self.text(24,y+25,prompt,16)
        self.circle(830,y+73,23,RED if enabled else BLACK)
        if enabled:self.text(830,y+56,'↑',27,WHITE,center=True)
        else:self.rect(821,y+64,18,18,WHITE,2)
    def title(self,title,sub):
        self.text(32,30,title,24,strong=True)
        self.text(32,73,sub,14)
    def close(self):
        self.circle(self.w-38,43,14,WHITE,BLACK)
        self.text(self.w-38,31,'×',19,center=True)
    def save(self,name,kind,position=None):
        text='<svg xmlns="http://www.w3.org/2000/svg" width="'+str(self.w)+'" height="'+str(self.h)+'" viewBox="0 0 '+str(self.w)+' '+str(self.h)+'">'+''.join(self.svg)+'</svg>'
        ET.fromstring(text)
        (OUT/(name+'.svg')).write_text(text,encoding='utf-8')
        self.image.resize((self.w,self.h),Image.Resampling.LANCZOS).save(OUT/(name+'.png'))
        inventory.append({'name':name,'type':kind,'width':self.w,'height':self.h,'position':position,'labels':self.labels})

def state(name,title,lines,buttons,badge=None,question=True):
    c=Canvas()
    if question:c.question(question if isinstance(question,str) else '把基础伤害骰数量翻倍，保留其他效果。')
    c.answer(title)
    for i,s in enumerate(lines):c.text(52,151+i*32,s,16)
    if badge:c.chip(52,286,220,badge,True)
    for i,(label,primary) in enumerate(buttons):c.button(52+i*210,342,196,label,primary)
    c.composer(prompt='处理中，请稍候。' if title.startswith('正在') else '需要调整哪里？继续告诉我们。',enabled=not title.startswith('正在'))
    c.save(name,'内容状态',(280,270))
    return c

# The fourth core page.
c=Canvas(1440,1000)
c.circle(84,45,18,RED);c.star(84,45,11,WHITE)
c.text(117,32,'MOD—SUPERMAN',20,strong=True);c.chip(1230,25,136,'＋ 新的修改')
c.line(64,88,1376,88)
logo=ROOT/'design/assets/bg3-logo-clear-transparent-2x.png'
if logo.exists():
    pic=Image.open(logo).convert('RGBA');pic.thumbnail((150,94),Image.Resampling.LANCZOS)
    x,y=(1440-pic.width)//2,100
    c.image.paste(pic.resize((pic.width*2,pic.height*2),Image.Resampling.LANCZOS),(x*2,y*2),pic.resize((pic.width*2,pic.height*2),Image.Resampling.LANCZOS))
    encoded=base64.b64encode(logo.read_bytes()).decode()
    c.svg.append(f'<image x="{x}" y="{y}" width="{pic.width}" height="{pic.height}" href="data:image/png;base64,{encoded}"/>')
c.text(720,206,'个性化Mod生成器',28,strong=True,center=True)
c.avatar(298,303);c.text(336,286,'修改文件已准备好',26,strong=True)
c.text(336,332,'第一滴血短剑 · 基础伤害 1d6 → 2d6',18)
c.text(336,365,'制作编号：DEMO-001',13)
c.line(336,405,1160,405)
for y,left,right in [(431,'文件生成','已生成'),(478,'交付内容','修改文件、修改清单、使用说明'),(525,'安装与游戏验证','等待你的操作与反馈')]:
    c.text(336,y,left,15);c.text(640,y,right,15)
c.line(336,568,1160,568)
c.button(336,596,218,'下载修改文件');c.button(570,596,210,'安装与验证说明',False)
c.text(336,678,'下载之后',16,strong=True)
c.text(336,710,'按说明完成必要的本地步骤，再检查游戏中的修改效果。',15)
c.text(336,742,'文件生成成功不代表已经安装或游戏验证通过。',14)
c.button(336,805,186,'成功使用',False);c.button(540,805,186,'遇到问题',False)
c.text(720,954,'原型预览：演示制作结果，不提供真实下载文件。',11,center=True)
c.save('04-结果下载页','完整页面')

# Overlays: all remain outside page frames on the Figma canvas.
c=Canvas(640,530);c.rect(0,0,640,530,WHITE,28,BLACK);c.title('选择修改对象','只展示目录内的对象，字段按对象能力开放。');c.close()
c.chip(32,113,112,'装备',True);c.chip(156,113,112,'技能')
c.rect(32,169,576,48,WHITE,24,BLACK);c.text(52,184,'搜索名称：第一滴血',14)
c.rect(32,239,576,108,YELLOW,20);c.text(54,258,'第一滴血短剑',20,strong=True);c.text(54,291,'武器 · 短剑  /  基础伤害 1d6',14);c.text(54,319,'可改：基础伤害、中文名、重量、稀有度',12)
c.text(32,377,'重名对象需核对区分信息；候选不等于全部已验证。',13)
c.button(32,446,230,'选择第一滴血短剑');c.button(278,446,150,'取消',False)
c.save('弹窗-A-装备选择','弹窗')
c=Canvas(640,530);c.rect(0,0,640,530,WHITE,28,BLACK);c.title('选择修改对象','技能首版保留治愈真言的限定能力。');c.close();c.chip(32,113,112,'装备');c.chip(156,113,112,'技能',True)
c.rect(32,169,576,48,WHITE,24,BLACK);c.text(52,184,'搜索名称：治愈真言',14)
c.rect(32,239,576,108,YELLOW,20);c.text(54,258,'治愈真言',20,strong=True);c.text(54,291,'技能  /  施法距离 18米',14);c.text(54,319,'可改：施法距离，其他技能字段尚未开放',12)
c.text(32,377,'36米历史方案获用户报告通过，本次新包仍需验证。',13)
c.button(32,446,230,'选择治愈真言');c.button(278,446,150,'取消',False);c.save('弹窗-B-技能选择','弹窗')
c=Canvas(640,440);c.rect(0,0,640,440,WHITE,28,BLACK);c.title('没有找到匹配对象','请尝试其他关键词，或返回对象目录。');c.close();c.rect(32,133,576,48,WHITE,24,BLACK);c.text(52,148,'搜索名称：未收录的对象',14);c.circle(320,239,26,YELLOW);c.text(320,220,'?',30,center=True);c.text(320,290,'不根据名称编造对象或内部标识。',14,center=True);c.button(32,352,210,'返回搜索');c.button(258,352,150,'取消',False);c.save('弹窗-C-搜索无结果','弹窗')

state('状态-01-解析中','正在整理你的修改期望…',['已保留当前对象和输入内容。','请稍候，无需重复提交。'],[('返回修改输入',False)],'处理中 · 请稍候')
state('状态-01-解析失败','暂时无法解析',['当前对象和输入内容已保留。','你可以重试，或直接填写允许的参数。'],[('重试解析',True),('直接填写参数',False)])
state('状态-01-不支持需求','这个修改暂不支持',['第一滴血短剑暂不支持修改攻击动画。','可调整基础伤害、中文名、重量和稀有度。'],[('调整修改需求',True)],question='把第一滴血短剑的攻击动画换掉。')
state('状态-02-需要澄清','你想修改哪一种伤害？',['“伤害翻倍”可能有多种含义。','本对象开放基础伤害骰；不会把总伤害直接翻倍。'],[('基础伤害骰翻倍',True),('重新描述',False)],question='把伤害翻倍。')

for name,title,value,hint in [
 ('状态-02-参数编辑','调整参数后，需要重新确认。','3d6','此示例目标值没有对应的本次游戏验证。'),
 ('状态-02-参数无效','请检查基础伤害格式。','20d6','骰数1～10，骰面限4、6、8、10、12、20。')]:
 c=Canvas();c.question();c.answer(title);c.text(52,152,'第一滴血短剑 · 仅编辑本次基础伤害',16);c.line(52,201,880,201);c.text(52,235,'原值 1d6',16);c.text(537,235,'目标值',14);c.chip(640,220,180,value,True);c.line(52,281,880,281);c.text(52,311,hint,14,RED if value=='20d6' else BLACK);c.text(52,341,'这是预设编辑状态，实际输入在开发后实现。',12)
 c.button(52,389,230,'修正为2d6' if value=='20d6' else '重新确认参数');c.button(298,389,150,'取消修改',False);c.composer(478);c.save(name,'内容状态',(280,270))

state('状态-03-生成中','正在生成修改文件…',['已收到你确认的参数：第一滴血短剑 1d6 → 2d6。','程序正在校验并生成；完成后展示实际阶段结果。'],[],'处理中 · 请勿重复提交')
state('状态-03-生成失败','未能完成文件生成',['已保留确认方案，本次没有成功下载文件。','失败阶段：文件生成。你可以重试或返回调整参数。'],[('重试生成',True),('返回参数',False)])

for phase in ['结果','确认']:
 c=Canvas();c.question('把治愈真言的施法距离改为36米。');c.answer('参数已确认。' if phase=='确认' else '请确认技能距离修改。');c.text(52,152,'治愈真言施法距离从18米改为36米。',17);c.text(52,184,'治疗量、消耗及其他配置不主动修改。',17);c.line(52,231,880,231);c.text(52,259,'施法距离（米）',15);c.text(629,254,'18',23);c.text(691,257,'→',21);c.chip(746,248,134,'36',True);c.line(52,306,880,306);c.text(52,335,'本次新包及精确距离边界、升环效果仍需验证。',14);c.button(52,389,230,'生成修改文件' if phase=='确认' else '确认参数');c.button(298,389,160,'继续调整',False);c.composer(478);c.save('状态-技能-'+phase,'内容状态',(280,270))
c=Canvas(880,216);c.rect(0,0,880,216,WHITE,28,BLACK);c.text(26,28,'修改对象',12);c.chip(102,16,270,'治愈真言 · 技能',True);c.text(26,90,'例如：把治愈真言的施法距离改为36米。',18);c.circle(830,173,23,RED);c.text(830,155,'↑',28,WHITE,center=True);c.save('首页补丁-技能输入','局部组件',(280,418))

c=Canvas(640,590);c.rect(0,0,640,590,WHITE,28,BLACK);c.title('安装与验证说明','先读本次说明，再进行本地操作。');c.close()
for y,n,title,detail in [(134,'01','核对本次修改','检查对象、参数、适用版本和影响范围。'),(225,'02','按实际文件完成本地步骤','是否需要打包，以下载说明中的实际内容为准。'),(316,'03','检查游戏效果','停用同对象旧包，按说明启用并对照修改。'),(407,'04','记录并反馈','生效或异常分别反馈，停用方法见下载说明。')]:
 c.circle(49,y+12,16,YELLOW);c.text(49,y+3,n,11,center=True);c.text(80,y,title,17,strong=True);c.text(80,y+33,detail,13)
c.button(32,516,230,'知道了');c.save('弹窗-D-安装与验证说明','弹窗')
c=Canvas(640,570);c.rect(0,0,640,570,WHITE,28,BLACK);c.title('告诉我们遇到了什么问题','制作编号：DEMO-001 · 第一滴血短剑');c.close();c.text(32,124,'问题发生在哪一步？',15,strong=True)
for x,w,t,sel in [(32,120,'生成',False),(164,120,'打包',False),(296,120,'安装',True),(428,160,'效果不符',False)]:c.chip(x,163,w,t,sel)
c.rect(32,230,576,142,WHITE,22,BLACK);c.text(54,252,'启用后没有看到预期变化。',16);c.text(32,400,'可提供：游戏版本、启用包、截图和实际表现。',13);c.text(32,431,'此原型使用预填示例，不实际提交反馈。',12);c.button(32,483,220,'提交反馈');c.button(268,483,150,'取消',False);c.save('弹窗-E-问题反馈','弹窗')
c=Canvas(560,320);c.rect(0,0,560,320,WHITE,28,BLACK);c.close();c.circle(280,76,26,YELLOW);c.line(267,75,277,85);c.line(277,85,295,66);c.text(280,127,'反馈已记录',24,strong=True,center=True);c.text(280,175,'原型状态演示，尚未实际保存用户反馈。',13,center=True);c.button(170,236,220,'返回制作结果');c.save('弹窗-F-反馈完成','弹窗')
c=Canvas(560,320);c.rect(0,0,560,320,WHITE,28,BLACK);c.close();c.text(32,46,'下载操作预览',23,strong=True);c.text(32,107,'实际产品在这里下载修改文件与使用说明。',15);c.text(32,146,'当前原型不提供真实Mod文件。',15);c.button(32,230,220,'返回制作结果');c.save('弹窗-G-下载预览','弹窗')
c=Canvas(560,340);c.rect(0,0,560,340,WHITE,28,BLACK);c.close();c.text(32,46,'下载没有完成',23,strong=True);c.text(32,107,'制作结果已保留，请重试下载。',15);c.text(32,146,'本状态用于验证下载失败后的恢复入口。',14);c.button(32,248,220,'重试下载');c.save('弹窗-H-下载失败','弹窗')

# A compact contact sheet for visual review.
columns=3;tw,th=460,355
rows=math.ceil(len(inventory)/columns)
sheet=Image.new('RGB',(columns*tw,rows*th),WHITE);d=ImageDraw.Draw(sheet)
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',15)
for i,item in enumerate(inventory):
 x,y=(i%columns)*tw,(i//columns)*th
 d.text((x+12,y+10),item['name'],font=font,fill=BLACK)
 im=Image.open(OUT/(item['name']+'.png'));im.thumbnail((tw-24,th-56),Image.Resampling.LANCZOS)
 sheet.paste(im,(x+(tw-im.width)//2,y+40))
 d.rectangle((x,y,x+tw-1,y+th-1),outline=BLACK)
sheet.save(OUT/'总览.png')
(OUT/'文件清单.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'files':len(inventory),'svg_structure':'passed','text_bounds':'passed','directory':str(OUT)},ensure_ascii=False))
