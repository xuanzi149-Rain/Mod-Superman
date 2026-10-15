from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

OUT=Path(__file__).parent
S=2; W=1600; H=1100
R='#EF1918'; K='#090909'; Y='#FFE600'; F='#FFFFFF'
fonts={'body':'msyh.ttc','bold':'msyhbd.ttc','serif':'simsun.ttc','latin':'timesbd.ttf'}
def font(size,kind='body'): return ImageFont.truetype('C:/Windows/Fonts/'+fonts[kind],int(size*S))
def rect(x,y,w,h,c,outline=None,width=1):
    d.rectangle((x*S,y*S,(x+w)*S,(y+h)*S),fill=c,outline=outline,width=width*S)
def line(x,y,x2,y2,c=F,width=1): d.line((x*S,y*S,x2*S,y2*S),fill=c,width=width*S)
def text(x,y,t,size=20,c=F,kind='body'):
    d.text((x*S,y*S),t,font=font(size,kind),fill=c,anchor='lt')
def poly(points,c): d.polygon([(x*S,y*S) for x,y in points],fill=c)
def circle(x,y,r,c): d.ellipse(((x-r)*S,(y-r)*S,(x+r)*S,(y+r)*S),fill=c)
def center(x,y,w,h,t,size=20,c=K,kind='bold'):
    ft=font(size,kind); b=d.textbbox((0,0),t,font=ft); tw=d.textlength(t,font=ft)/S
    text(x+(w-tw)/2,y+(h-(b[3]-b[1])/S)/2,t,size,c,kind)
def button(x,y,w,t,primary=True):
    if primary: poly([(x+20,y),(x+w,y),(x+w-20,y+58),(x,y+58)],Y)
    else: rect(x,y,w,58,None,F)
    center(x,y,w,58,t,18,K if primary else F)
def star(x,y,r,c):
    poly([(x+math.cos(i*math.pi/8)* (r if i%2==0 else r*.4),y+math.sin(i*math.pi/8)*(r if i%2==0 else r*.4)) for i in range(16)],c)
def base(n,eyebrow,headline,subhead):
    global im,d
    im=Image.new('RGB',(W*S,H*S),K); d=ImageDraw.Draw(im)
    rect(96,0,1016,H,R)
    poly([(48,35),(72,59),(48,83),(24,59)],R)
    for i,(a,b) in enumerate([('01','描述'),('02','确认'),('03','生成'),('04','下载')],1):
        yy=214+(i-1)*171
        if i==n: rect(0,yy-17,4,91,Y)
        text(32,yy,a,20,Y if i==n else F,'latin')
        text(35,yy+33,b[0],15,Y if i==n else F); text(35,yy+55,b[1],15,Y if i==n else F)
    text(28,1047,'BG3',16,R,'latin')
    text(150,40,'MOD—SUPERMAN',23,K,'bold')
    text(896,45,'＋ 新的修改',17,K)
    line(150,89,1058,89,K)
    text(150,120,'博德之门3个性化Mod生成器',17,K,'bold')
    logo=Image.open(OUT.parent/'assets/bg3-logo-clear-transparent-2x.png').convert('RGBA')
    logo.thumbnail((150*S,94*S),Image.Resampling.LANCZOS)
    im.paste(logo,(894*S,100*S),logo)
    text(150,173,headline,79,K,'bold')
    text(150,276,subhead,79,K,'bold')
    line(150,397,1058,397,K)
    text(150,418,f'0{n} / 04',18,K,'latin')
    text(280,417,['选择对象，描述你的修改期望','先看清参数，再决定是否确认','确认完成，准备生成修改文件','下载文件，完成本地安装与验证'][n-1],19,K)
    # Repeated outlined geometric motif, contained behind the main content.
    d.arc((650*S,453*S,1260*S,1063*S),180,350,fill=K,width=2*S)
    star(1016,365,19,K)
    text(1158,52,['修改助手','修改说明','生成准备','交付说明'][n-1],35,Y,'serif')
    rect(1158,110,394,5,R)
    text(1158,148,'当前对象 / 装备',15,Y)
    text(1158,179,'第一滴血短剑',27,F,'bold')
    line(1158,234,1552,234,F)
    text(150,1052,'博德之门 3 / 个性化 Mod 制作',14,K)
    text(864,1052,'设计预览 · 示例数据',14,K)
def side_block(y,title,rows):
    text(1158,y,title,17,Y,'bold')
    for i,row in enumerate(rows): text(1158,y+38+i*30,row,18,F)
def card():
    rect(169,504,889,506,Y); rect(150,485,889,506,K)
def foot_side(n):
    line(1158,882,1552,882,F)
    text(1158,910,'制作流程',16,Y)
    for i,t in enumerate(['描述期望','确认参数','生成文件','下载与验证'],1):
        x=1158+((i-1)%2)*205; y=952+((i-1)//2)*47
        circle(x+10,y+10,10,Y if i==n else F)
        center(x,y,20,20,str(i),12,K)
        text(x+28,y,t,15,Y if i==n else F)
def save(name): im.save(OUT/(name+'.png')); return im.resize((800,550),Image.Resampling.LANCZOS)

previews=[]
base(1,'个性化Mod生成器','生成你的','私人定制Mod！')
card()
text(190,524,'修改对象',17,Y)
rect(318,512,331,48,Y); center(318,512,331,48,'第一滴血短剑 · 装备',18)
text(190,601,'你想怎么修改？',32,F,'bold')
text(190,659,'例如：把基础伤害骰数量翻倍，',26,F)
text(190,703,'保留其他效果。',26,F)
line(190,792,999,792,F)
text(190,824,'试试这些想法',15,Y)
text(190,862,'↗ 基础伤害翻倍    ↗ 修改装备名称',18,F)
button(715,900,284,'解析修改期望  →')
side_block(272,'从一个具体想法开始',['选择一件装备或一个技能，','告诉我们你希望怎样改变它。'])
side_block(418,'你来决定，AI 帮你理解',['AI 会整理修改参数。','你确认后，才生成修改文件。'])
side_block(584,'保留清晰的修改边界',['只修改已支持的字段；','有歧义时，先补充说明。'])
foot_side(1); previews.append(save('01-需求输入'))

base(2,'博德之门3个性化生成器','看清每一处','再确认修改。')
card(); text(190,520,'你的期望',15,Y)
text(190,551,'把基础伤害骰数量翻倍，保留其他效果。',24,F)
line(190,609,999,609,F)
text(190,642,'已理解，先确认这次修改。',29,F,'bold')
text(190,704,'基础伤害',18,F)
center(481,676,180,68,'1d6',43,F,'latin'); center(664,676,70,68,'→',34,F)
rect(776,676,222,68,Y); center(776,676,222,68,'2d6',43,K,'latin')
line(190,777,999,777,F)
text(190,808,'仅修改基础伤害字段，其他配置不主动改写。',19,F)
button(190,900,211,'继续调整',False); button(716,900,282,'确认参数  →')
side_block(272,'这次会发生什么',['基础伤害骰由 1 个增加到 2 个。','骰子面数保持为 6。'])
side_block(432,'影响范围',['可能影响共用该记录的装备，','不承诺只修改一个实例。'])
side_block(592,'还需要调整？',['点击「继续调整」补充期望。','参数变化后，需要重新确认。'])
foot_side(2); previews.append(save('02-参数确认'))

base(3,'博德之门3个性化生成器','参数已确认','现在，生成。')
card(); text(190,522,'已确认的修改',16,Y)
text(190,562,'第一滴血短剑',30,F,'bold')
line(190,627,999,627,F)
text(190,670,'基础伤害',18,F); center(481,638,180,70,'1d6',43,F,'latin')
center(664,638,70,70,'→',34,F); rect(776,638,222,70,Y); center(776,638,222,70,'2d6',43,K,'latin')
line(190,748,999,748,F)
text(190,784,'准备生成',16,Y)
text(190,822,'修改文件  /  修改清单  /  使用说明',22,F)
button(190,900,211,'继续调整',False); button(700,900,298,'生成修改文件  →')
side_block(272,'确认已完成',['将按当前参数生成修改文件，','不会直接改动你的游戏。'])
side_block(432,'生成之后',['下载文件和使用说明，','在电脑上完成打包与安装。'])
side_block(592,'改变想法也没关系',['仍可返回继续调整。','修改参数后，请重新确认。'])
foot_side(3); previews.append(save('03-确认后生成'))

base(4,'博德之门3个性化生成器','修改已就绪','带进你的游戏。')
card(); text(190,520,'生成结果 / 示例',16,Y)
text(190,559,'第一滴血短剑',30,F,'bold')
text(190,612,'基础伤害  1d6 → 2d6',25,F)
line(190,673,999,673,F)
for yy,num,title,detail in [(703,'01','修改文件','用于本地打包'),(760,'02','修改清单','核对字段与参数'),(817,'03','使用说明','打包、安装与验证步骤')]:
    text(190,yy,num,20,Y,'latin'); text(240,yy,title,20,F,'bold'); text(617,yy,detail,18,F)
button(190,900,228,'安装与验证说明',False); button(700,900,298,'下载修改文件  ↓')
side_block(272,'下一步：本地验证',['1. 按说明打包并安装','2. 进入游戏检查修改效果','3. 返回这里反馈结果'])
side_block(459,'请区分制作与验证',['文件生成成功，并不代表','安装或游戏验证已通过。'])
text(1158,601,'验证后告诉我们',17,Y,'bold')
button(1158,648,180,'成功使用',False); button(1354,648,198,'遇到问题',False)
text(1158,758,'当前为视觉预览，',15,F); text(1158,785,'不提供真实文件下载或反馈提交。',15,F)
foot_side(4); previews.append(save('04-下载与验证'))

sheet=Image.new('RGB',(1640,1180),'#FFFFFF')
sd=ImageDraw.Draw(sheet)
for i,p in enumerate(previews):
    x=10+(i%2)*820; y=35+(i//2)*590
    sd.text((x,y-27),['01 需求输入','02 参数确认','03 确认后生成','04 下载与验证'][i],font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',18),fill=K)
    sheet.paste(p,(x,y))
sheet.save(OUT/'四页总览.png')
print('Rendered 4 pages at 3200 × 2200, plus overview.')
