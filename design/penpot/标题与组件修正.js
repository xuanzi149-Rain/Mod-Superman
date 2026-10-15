const B=storage.boards;
await penpot.currentFile.saveVersion('标题与组件调整前 · 2026-10-13');
const shapes=b=>penpotUtils.findShapes(()=>true,b);
const leaves=b=>shapes(b).filter(s=>!s.children?.length);
const results=[];
for(const [name,b] of Object.entries(B)){
 if(b.width!==1440)continue;
 const all=shapes(b),title=all.find(s=>s.type==='text'&&/生成器/.test(s.characters));
 const logo=all.find(s=>s.name==='Baldur’s Gate 3 标志');
 if(!b.getPluginData('header-v2')){
  if(name==='01-问答首页'){
   if(logo){logo.hidden=false;logo.x=b.x+637.5;logo.y=b.y+116;}
   if(title){title.y=b.y+254;title.x=b.x+(1440-title.width)/2;}
   for(const s of leaves(b)){
    if(s.type==='text'&&s.characters==='生成你的私人定制Mod！')s.y=b.y+318;
    if(s.type!=='text'&&s.x-b.x>200&&s.y-b.y>220&&s.y-b.y<300&&s.width<500)s.y+=75;
   }
  }else{
   if(logo)logo.hidden=true;
   if(title){title.characters='博德之门3个性化生成器';title.name='页面标题';title.y=b.y+136;title.fontSize='28';}
   const homeLike=['01-治愈真言','01-修改中文名','测试-搜索无结果'].includes(name);
   for(const s of leaves(b)){
    if(s===title||s===logo)continue;
    const y=s.y-b.y;
    if(homeLike){
     if(s.type==='text'&&s.characters==='生成你的私人定制Mod！')s.hidden=true;
     if(s.type!=='text'&&s.x-b.x>200&&y>220&&y<300&&s.width<500)s.hidden=true;
     if(y>=418)s.y-=166;
    }else if(y>=270)s.y-=66;
   }
  }
  b.setPluginData('header-v2','2026-10-13');
 }
 // Replace glyph arrows and old stroke fragments with a single centred vector.
 const circles=shapes(b).filter(s=>s.type==='ellipse'&&s.width>=40&&s.width<=60&&s.x-b.x>900&&s.fills?.some(f=>f.fillColor?.toUpperCase()==='#D71920'));
 for(const circle of circles){
  if(circle.getPluginData('arrow-v2'))continue;
  const cx=circle.x+circle.width/2,cy=circle.y+circle.height/2;
  for(const s of leaves(b)){
   if(s===circle||s.interactions?.length)continue;
   const isGlyph=s.type==='text'&&s.characters==='↑'&&Math.abs(s.x-cx)<40&&Math.abs(s.y-cy)<40;
   const contained=['path','svg-raw'].includes(s.type)&&s.x>=circle.x&&s.y>=circle.y&&s.x+s.width<=circle.x+circle.width&&s.y+s.height<=circle.y+circle.height;
   if(isGlyph||contained)s.hidden=true;
  }
  const icon=penpot.createShapeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="24" viewBox="0 0 20 24"><path d="M10 22V2M2 10L10 2L18 10" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');
  b.appendChild(icon);icon.name='发送箭头-居中';icon.x=cx-10;icon.y=cy-12;
  const hits=shapes(b).filter(s=>s.type==='rectangle'&&s.interactions?.length&&s.width<=60&&s.height<=60&&Math.abs(s.x+s.width/2-cx)<40&&Math.abs(s.y+s.height/2-cy)<40);
  for(const h of hits){h.resize(circle.width,circle.height);h.x=circle.x;h.y=circle.y;h.borderRadius=circle.width/2;h.bringToFront();}
  circle.resize(46,46);circle.x=cx-23;circle.y=cy-23;circle.setPluginData('arrow-v2','2026-10-13');
 }
 results.push({name,logo:name==='01-问答首页',sendButtons:circles.length});
}
storage.headerRevision=results;
return {pages:results.length,sendButtons:results.reduce((n,p)=>n+p.sendButtons,0)};
