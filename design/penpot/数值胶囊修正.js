const changed=[];
for(const [name,b] of Object.entries(storage.boards)){
 const all=penpotUtils.findShapes(()=>true,b);
 for(const t of all.filter(t=>t.type==='text'&&!t.hidden&&/^(?:[123]d6|18|36|20d6)$/.test(t.characters))){
  const r=all.find(s=>s.type==='rectangle'&&s.width>=90&&s.width<=240&&s.height>=30&&s.height<=56&&s.fills?.some(f=>f.fillColor?.toUpperCase()==='#FFD600')&&t.x>=s.x-5&&t.x+t.width<=s.x+s.width+5&&t.y>=s.y-5&&t.y+t.height<=s.y+s.height+5);
  if(r){t.fontSize='22';t.fontWeight='500';t.growType='auto-width';changed.push({page:name,value:t.characters});}
 }
}
return changed;
