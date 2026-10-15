const B=storage.boards;
const find=(b,name)=>penpotUtils.findShape(s=>s.name===name,b);
function hit(b,label,x,y,w,h){let s=find(b,'点击-'+label);if(!s){s=penpot.createRectangle();b.appendChild(s);s.name='点击-'+label;s.resize(w,h);s.x=b.x+x;s.y=b.y+y;s.fills=[{fillColor:'#FFFFFF',fillOpacity:0}];s.strokes=[];}return s;}
function link(from,label,to,type='navigate-to',box){const b=B[from],s=box?hit(b,label,...box):find(b,'点击-'+label);if(!s)throw Error('Missing button '+from+' / '+label);s.interactions.forEach(i=>s.removeInteraction(i));const action=type==='close-overlay'?{type,destination:b}:{type,destination:B[to],...(type==='open-overlay'?{position:'center',closeWhenClickOutside:true,addBackgroundOverlay:false}:{})};s.addInteraction('click',action);}
const nav=(f,l,t,box)=>link(f,l,t,'navigate-to',box);
const overlay=(f,l,t,box)=>link(f,l,t,'open-overlay',box);
const close=(f,l,box)=>link(f,l,null,'close-overlay',box);
for(const [name,b] of Object.entries(B)){
 for(const s of penpotUtils.findShapes(s=>s.type==='text',b)){
  if(s.characters==='个性化Mod生成器')s.x=b.x+(b.width-s.width)/2;
  if(s.characters==='博德之门3个性化Mod生成器'){s.characters='个性化Mod生成器';s.x=b.x+(b.width-s.width)/2;}
 }
 if(b.width===1440)nav(name,'新的修改','01-问答首页',[1230,25,136,40]);
 if(name.startsWith('弹窗-'))close(name,'关闭',[b.width-56,24,36,36]);
}
for(const name of ['01-问答首页','01-治愈真言']){
 const b=B[name];const title=find(b,'生成你的私人定制Mod！');if(title)title.x=b.x+(1440-title.width)/2;
 for(const s of penpotUtils.findShapes(s=>s.type==='text',b))if(['一次修改一个对象','描述具体期望，参数由你最终确认','检查参数差异与影响范围。','选定对象，输入修改期望。','按说明操作，反馈游戏效果。'].includes(s.characters))s.hidden=true;
 for(const s of penpotUtils.findShapes(s=>s.type==='ellipse'&&s.width<10&&s.parentY>100&&s.parentY<200,b))s.hidden=true;
 const label=find(b,'看清，再确认');if(label)label.characters='确认具体要求';
 overlay(name,'选择对象','弹窗-A-装备选择',[378,435,258,36]);
 nav(name,'发送',name==='01-问答首页'?'01-解析中':'技能-结果',[1087,567,46,46]);
 nav(name,'伤害示例','01-问答首页',[418,660,180,40]);
 nav(name,'距离示例','01-治愈真言',[823,660,210,40]);
}
nav('02-问答结果','确认参数','03-确认后状态',[332,648,210,48]);
nav('02-问答结果','继续调整','02-参数编辑',[556,648,146,48]);
nav('02-问答结果','发送调整','02-参数编辑',[1087,823,46,46]);
for(const [f,t] of [['03-确认后状态','03-生成中'],['03-确认3d6','03-生成3d6']]){
 nav(f,'生成修改文件',t,[332,648,210,48]);nav(f,'继续调整','02-参数编辑',[556,648,146,48]);nav(f,'发送调整','02-参数编辑',[1087,823,46,46]);
}
for(const [f,t,ms] of [['01-解析中','02-问答结果',800],['03-生成中','04-结果下载页',1000],['03-生成3d6','04-结果3d6',1000]]){
 const b=B[f];b.interactions.forEach(i=>b.removeInteraction(i));b.addInteraction('after-delay',{type:'navigate-to',destination:B[t]},ms);
}
nav('01-解析中','返回修改输入','01-问答首页');nav('01-解析失败','重试解析','01-解析中');nav('01-解析失败','直接填写参数','02-参数编辑');nav('01-不支持需求','调整修改需求','01-问答首页');
nav('02-参数编辑','重新确认参数','03-确认3d6');nav('02-参数编辑','取消修改','02-问答结果');nav('02-参数无效','修正为2d6','02-问答结果');nav('02-参数无效','取消修改','02-问答结果');
nav('02-需要澄清','基础伤害骰翻倍','02-问答结果');nav('02-需要澄清','重新描述','01-问答首页');nav('03-生成失败','重试生成','03-生成中');nav('03-生成失败','返回参数','02-问答结果');
nav('技能-结果','确认参数','技能-确认');nav('技能-结果','继续调整','01-治愈真言');nav('技能-确认','生成修改文件','04-技能下载');nav('技能-确认','继续调整','01-治愈真言');
nav('弹窗-A-装备选择','选择第一滴血短剑','01-问答首页');nav('弹窗-B-技能选择','选择治愈真言','01-治愈真言');
overlay('弹窗-A-装备选择','技能标签','弹窗-B-技能选择',[160,110,110,36]);overlay('弹窗-B-技能选择','装备标签','弹窗-A-装备选择',[32,110,110,36]);
for(const f of ['弹窗-A-装备选择','弹窗-B-技能选择','弹窗-C-搜索无结果','弹窗-E-问题反馈'])close(f,'取消');
overlay('弹窗-C-搜索无结果','返回搜索','弹窗-A-装备选择');close('弹窗-D-安装与验证说明','知道了');
overlay('弹窗-E-问题反馈','提交反馈','弹窗-F-反馈完成');overlay('弹窗-H-下载失败','重试下载','弹窗-G-下载预览');
for(const f of ['弹窗-F-反馈完成','弹窗-G-下载预览'])close(f,'返回制作结果');
for(const f of ['04-结果下载页','04-结果3d6','04-技能下载']){
 overlay(f,'下载修改文件','弹窗-G-下载预览');overlay(f,'安装与验证说明','弹窗-D-安装与验证说明');overlay(f,'成功使用','弹窗-F-反馈完成');overlay(f,'遇到问题','弹窗-E-问题反馈');
}
const flowNames=new Set(penpot.currentPage.flows.map(f=>f.name));
for(const [label,name] of [['01 装备完整流程','01-问答首页'],['02 参数调整与重新确认','02-参数编辑'],['03 技能完整流程','01-治愈真言'],['04 澄清需求','02-需要澄清'],['05 解析失败恢复','01-解析失败'],['06 不支持需求','01-不支持需求'],['07 参数校验','02-参数无效'],['08 生成失败恢复','03-生成失败']])if(!flowNames.has(label))penpot.currentPage.createFlow(label,B[name]);
storage.logo.hidden=true;
return {boards:Object.keys(B).length,interactions:penpotUtils.findShapes(s=>s.interactions?.length>0,penpot.root).reduce((n,s)=>n+s.interactions.length,0),flows:penpot.currentPage.flows.map(f=>f.name)};
