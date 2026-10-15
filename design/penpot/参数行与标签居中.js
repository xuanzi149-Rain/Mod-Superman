storage.alignmentPreVersion={status:'saving'};
penpot.currentFile.saveVersion('参数行文字居中调整前 · 2026-10-13').then(()=>storage.alignmentPreVersion={status:'saved'}).catch(e=>storage.alignmentPreVersion={status:'failed',error:String(e)});
const rows=[],pills=[],numbers=[];
for(const [name,b] of Object.entries(storage.boards)){
 const all=penpotUtils.findShapes(()=>true,b),texts=all.filter(s=>s.type==='text'&&!s.hidden);
 const yellow=all.filter(s=>s.type==='rectangle'&&s.width>=60&&s.width<=300&&s.height>=30&&s.height<=56&&s.fills?.some(f=>f.fillColor?.toUpperCase()==='#FFD600'));
 for(const r of yellow){
  const inside=texts.filter(t=>t.x+t.width/2>=r.x&&t.x+t.width/2<=r.x+r.width&&t.y+t.height/2>=r.y&&t.y+t.height/2<=r.y+r.height&&t.width<=r.width-12&&t.height<=r.height);
  if(inside.length===1){const t=inside[0];t.x=r.x+(r.width-t.width)/2;t.y=r.y+(r.height-t.height)/2;pills.push({page:name,text:t.characters});}
 }
 for(const arrow of texts.filter(t=>t.characters==='→')){
  const r=yellow.find(r=>r.x>arrow.x&&Math.abs((r.y+r.height/2)-(arrow.y+arrow.height/2))<45);
  if(!r)continue;
  const cy=r.y+r.height/2,cx=r.x+r.width/2;
  const before=texts.find(t=>['第一滴血短剑','1d6','18'].includes(t.characters)&&t.x<arrow.x&&Math.abs(t.y+t.height/2-cy)<45);
  const label=texts.find(t=>['基础伤害','中文名称','施法距离（米）'].includes(t.characters)&&Math.abs(t.y+t.height/2-cy)<45);
  arrow.x=cx-100-arrow.width/2;arrow.y=cy-arrow.height/2;
  if(before){before.x=cx-200-before.width/2;before.y=cy-before.height/2;}
  if(label)label.y=cy-label.height/2;
  rows.push({page:name,original:before?.characters,centerY:cy-b.y});
 }
 for(const t of texts.filter(t=>/^(?:01|02|03|×)$/.test(t.characters))){
  const c=all.find(s=>s.type==='ellipse'&&s.width>=24&&s.width<=36&&Math.abs(s.x+s.width/2-t.x-t.width/2)<24&&Math.abs(s.y+s.height/2-t.y-t.height/2)<24);
  if(c){t.x=c.x+(c.width-t.width)/2;t.y=c.y+(c.height-t.height)/2;numbers.push(name);}
 }
}
storage.textAlignmentRevision={rows,pills,numbers:numbers.length};
return {parameterRows:rows,pillLabels:pills.length,circleLabels:numbers.length};
