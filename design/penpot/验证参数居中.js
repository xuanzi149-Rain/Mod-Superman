const issues=[];
for(const [name,b] of Object.entries(storage.boards)){
 const all=penpotUtils.findShapes(()=>true,b),texts=all.filter(s=>s.type==='text'&&!s.hidden);
 for(const a of texts.filter(t=>t.characters==='→')){
  const r=all.find(r=>r.type==='rectangle'&&r.width>=90&&r.width<=240&&r.height>=30&&r.height<=56&&r.x>a.x&&r.fills?.some(f=>f.fillColor?.toUpperCase()==='#FFD600')&&Math.abs(r.y+r.height/2-a.y-a.height/2)<40);
  if(!r)continue;
  const cy=r.y+r.height/2;
  for(const t of texts.filter(t=>['第一滴血短剑','曙光短剑','1d6','2d6','3d6','18','36','中文名称','基础伤害','施法距离（米）','→'].includes(t.characters)&&Math.abs(t.y+t.height/2-cy)<40))if(Math.abs(t.y+t.height/2-cy)>.1)issues.push({page:name,text:t.characters,offset:t.y+t.height/2-cy});
 }
}
return {issues,rows:storage.textAlignmentRevision.rows.length,pills:storage.textAlignmentRevision.pills.length};
