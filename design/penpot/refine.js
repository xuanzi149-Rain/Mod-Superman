const B=storage.boards;
const all=b=>penpotUtils.findShapes(()=>true,b);
const txt=b=>all(b).filter(s=>s.type==='text');
const find=(b,n)=>penpotUtils.findShape(s=>s.name===n,b);
function clone(source,name){if(B[name])return B[name];const b=B[source].clone();b.name=name;b.x=(Object.keys(B).length%5)*1580;b.y=Math.floor(Object.keys(B).length/5)*1180;for(const s of [b,...all(b)])s.interactions?.forEach(i=>s.removeInteraction(i));B[name]=b;return b;}
function nav(b,name,target){const s=find(b,'点击-'+name);if(!s)throw Error('Missing '+name);s.interactions.forEach(i=>s.removeInteraction(i));s.addInteraction('click',{type:'navigate-to',destination:target});}
function overlay(b,name,target){const s=find(b,'点击-'+name);if(!s)throw Error('Missing '+name);s.interactions.forEach(i=>s.removeInteraction(i));s.addInteraction('click',{type:'open-overlay',destination:target,position:'center',closeWhenClickOutside:true,addBackgroundOverlay:false});}
function hot(b,name,x,y,w,h){const s=penpot.createRectangle();b.appendChild(s);s.name='点击-'+name;s.resize(w,h);s.x=b.x+x;s.y=b.y+y;s.fills=[{fillColor:'#FFFFFF',fillOpacity:0}];s.strokes=[];return s;}
// Name-change example: every visible suggestion has a working, consistent path.
for(const [src,name] of [['01-问答首页','01-修改中文名'],['02-问答结果','02-中文名结果'],['03-确认后状态','03-中文名确认'],['04-结果下载页','04-中文名下载']]){
 const b=clone(src,name);for(const s of txt(b)){
  let v=s.characters;v=v.replace('例如：把基础伤害骰数量翻倍，保留其他效果。','例如：把中文名改为曙光短剑，保留其他效果。').replace('把基础伤害骰数量翻倍，保留其他效果。','把中文名改为曙光短剑，保留其他效果。').replace('第一滴血短剑的基础伤害骰由1个增加到2个。','第一滴血短剑的中文名将改为「曙光短剑」。').replace('仅修改基础伤害字段','仅修改中文名字段').replace('第一滴血短剑 · 基础伤害 1d6 → 2d6','第一滴血短剑 · 中文名 → 曙光短剑');
  if(v==='基础伤害')v='中文名称';if(v==='1d6'){v='第一滴血短剑';s.fontSize='16';s.x=b.x+810;}if(v==='2d6'){v='曙光短剑';s.fontSize='18';s.x=b.x+1060;}s.characters=v;
 }
 if(b.width===1440){if(!find(b,'点击-新的修改'))hot(b,'新的修改',1230,25,136,40);nav(b,'新的修改',B['01-问答首页']);}
}
for(const n of ['01-问答首页','01-治愈真言','01-修改中文名']){
 const b=B[n];hot(b,'名称示例',608,660,204,40);nav(b,'名称示例',B['01-修改中文名']);
 if(n==='01-修改中文名'){nav(b,'发送',B['02-中文名结果']);nav(b,'伤害示例',B['01-问答首页']);nav(b,'距离示例',B['01-治愈真言']);overlay(b,'选择对象',B['弹窗-A-装备选择']);}
}
nav(B['02-中文名结果'],'确认参数',B['03-中文名确认']);nav(B['02-中文名结果'],'继续调整',B['01-修改中文名']);nav(B['02-中文名结果'],'发送调整',B['01-修改中文名']);nav(B['03-中文名确认'],'生成修改文件',B['04-中文名下载']);nav(B['03-中文名确认'],'继续调整',B['01-修改中文名']);nav(B['03-中文名确认'],'发送调整',B['01-修改中文名']);
// Context-specific feedback avoids changing the result after a modal closes.
for(const [result,code,object] of [['04-结果下载页','DEMO-SWORD-2D6','第一滴血短剑'],['04-结果3d6','DEMO-SWORD-3D6','第一滴血短剑'],['04-技能下载','DEMO-HEAL-36','治愈真言'],['04-中文名下载','DEMO-NAME','第一滴血短剑']]){
 const b=B[result];for(const s of txt(b))if(s.characters.startsWith('制作编号：'))s.characters='制作编号：'+code;
 const e=clone('弹窗-E-问题反馈','反馈-'+code),f=clone('弹窗-F-反馈完成','反馈完成-'+code);
 for(const s of txt(e))if(s.characters.startsWith('制作编号：'))s.characters='制作编号：'+code+' · '+object;
 overlay(b,'遇到问题',e);overlay(b,'成功使用',f);overlay(b,'下载修改文件',B['弹窗-G-下载预览']);overlay(b,'安装与验证说明',B['弹窗-D-安装与验证说明']);
 overlay(e,'提交反馈',f);nav(e,'取消',b);nav(e,'关闭',b);nav(f,'返回制作结果',b);nav(f,'关闭',b);
}
nav(B['弹窗-C-搜索无结果'],'返回搜索',B['01-问答首页']);
// Independent failure flows keep demonstration controls off the real home page.
const search=clone('01-问答首页','测试-搜索无结果');overlay(search,'选择对象',B['弹窗-C-搜索无结果']);
for(const l of ['发送','名称示例','伤害示例','距离示例','新的修改'])if(find(search,'点击-'+l))nav(search,l,B['01-问答首页']);
const fail=clone('04-结果下载页','测试-下载失败');overlay(fail,'下载修改文件',B['弹窗-H-下载失败']);nav(fail,'新的修改',B['01-问答首页']);
for(const l of ['遇到问题','成功使用','安装与验证说明'])overlay(fail,l,B['弹窗-D-安装与验证说明']);
nav(B['弹窗-H-下载失败'],'重试下载',B['04-结果下载页']);
for(const f of penpot.currentPage.flows.slice())if(/^Flow \d+$/.test(f.name))penpot.currentPage.removeFlow(f);
const existing=new Set(penpot.currentPage.flows.map(f=>f.name));for(const [name,b] of [['09 中文名修改',B['01-修改中文名']],['10 搜索无结果',search],['11 下载失败恢复',fail]])if(!existing.has(name))penpot.currentPage.createFlow(name,b);
// Label the static limits once in prototype metadata, without claiming a real result.
penpot.currentPage.setPluginData('validation-status','静态交互原型；未调用模型、生成真实Mod、提交反馈或进行游戏验证。');
penpot.selection=[B['01-问答首页']];penpot.viewport.zoomIntoView([B['01-问答首页']]);
return {fileId:penpot.currentFile.id,pageId:penpot.currentPage.id,boards:Object.keys(B).length,flows:penpot.currentPage.flows.map(f=>f.name)};
