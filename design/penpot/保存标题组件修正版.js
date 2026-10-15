const B=storage.boards,b=B['技能-确认'];
const circle=penpotUtils.findShape(s=>s.type==='ellipse'&&s.width===46&&s.x-b.x>900&&s.fills?.some(f=>f.fillColor?.toUpperCase()==='#D71920'),b);
let h=penpotUtils.findShape(s=>s.name==='点击-发送调整',b);
if(!h){h=penpot.createRectangle();b.appendChild(h);h.name='点击-发送调整';}
h.resize(46,46);h.x=circle.x;h.y=circle.y;h.borderRadius=23;h.fills=[{fillColor:'#FFFFFF',fillOpacity:0}];h.strokes=[];
if(!h.interactions.some(i=>i.action.destination?.id===B['01-治愈真言'].id))h.addInteraction('click',{type:'navigate-to',destination:B['01-治愈真言']});
h.bringToFront();
await penpot.currentFile.saveVersion('首页标题与发送组件修正 · 2026-10-13');
for(const name of ['02-问答结果','技能-结果']){
 storage.revisionRenders[name]={status:'exporting'};
 B[name].export({type:'png'}).then(bytes=>{let str='';for(let i=0;i<bytes.length;i+=8192)str+=String.fromCharCode(...bytes.slice(i,i+8192));storage.revisionRenders[name]={status:'ready',base64:btoa(str),bytes:bytes.length};}).catch(e=>storage.revisionRenders[name]={status:'failed',error:String(e)});
}
penpot.selection=[B['01-问答首页']];penpot.viewport.zoomIntoView([B['01-问答首页']]);
return {saved:true,label:'首页标题与发送组件修正 · 2026-10-13'};
