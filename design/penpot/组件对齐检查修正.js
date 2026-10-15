const B=storage.boards,issues=[];
let labels=0,closeIcons=0;
for(const [name,b] of Object.entries(B)){
 const all=penpotUtils.findShapes(()=>true,b),texts=all.filter(s=>s.type==='text'&&!s.hidden);
 const title=texts.find(s=>s.name==='页面标题');if(title)title.x=b.x+(b.width-title.width)/2;
 // Centre button labels using their actual rendered text bounds.
 for(const h of all.filter(s=>s.type==='rectangle'&&s.interactions?.length&&s.width>=90&&s.width<=250&&s.height>=32&&s.height<=50)){
  const candidates=texts.filter(t=>t!==title&&Number(t.fontSize)<=18&&t.x>=h.x-5&&t.y>=h.y-5&&t.x+t.width<=h.x+h.width+5&&t.y+t.height<=h.y+h.height+5);
  if(candidates.length===1){const t=candidates[0];t.x=h.x+(h.width-t.width)/2;t.y=h.y+(h.height-t.height)/2;labels++;}
 }
 // Keep numeric pills and the close icon centred as well.
 for(const t of texts.filter(t=>t.characters==='×')){
  const c=all.find(s=>s.type==='ellipse'&&s.width<=36&&Math.abs(s.x+s.width/2-(t.x+t.width/2))<30&&Math.abs(s.y+s.height/2-(t.y+t.height/2))<30);
  if(c){t.x=c.x+(c.width-t.width)/2;t.y=c.y+(c.height-t.height)/2;closeIcons++;}
 }
 for(const t of texts.filter(t=>/^(?:[123]d6|18|36|20d6)$/.test(t.characters))){
  const r=all.find(s=>s.type==='rectangle'&&s.width>=90&&s.width<=240&&s.height>=30&&s.height<=56&&s.fills?.some(f=>f.fillColor?.toUpperCase()==='#FFD600')&&t.x>=s.x-5&&t.x+t.width<=s.x+s.width+5&&t.y>=s.y-5&&t.y+t.height<=s.y+s.height+5);
  if(r){t.x=r.x+(r.width-t.width)/2;t.y=r.y+(r.height-t.height)/2;}
 }
 const logos=all.filter(s=>s.name==='Baldur’s Gate 3 标志'&&!s.hidden);
 if(b.width===1440&&name!=='01-问答首页'&&logos.length)issues.push(name+' has logo');
 const circles=all.filter(s=>s.type==='ellipse'&&s.width>=40&&s.width<=60&&s.x-b.x>900&&s.fills?.some(f=>f.fillColor?.toUpperCase()==='#D71920'));
 for(const c of circles){
  const icon=all.find(s=>s.name==='发送箭头-居中'&&Math.abs(s.x+s.width/2-c.x-c.width/2)<2&&Math.abs(s.y+s.height/2-c.y-c.height/2)<2);
  if(!icon)issues.push(name+' arrow not centred');
  if(Math.abs(c.width-c.height)>.01)issues.push(name+' circle is not round');
 }
}
return {labelsCentred:labels,closeIconsCentred:closeIcons,issues};
