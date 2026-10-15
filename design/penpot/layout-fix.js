const B=storage.boards;
for(const name of ['02-问答结果','03-确认后状态','03-确认3d6','02-中文名结果','03-中文名确认']){
 const b=B[name];if(b.getPluginData('body-shifted'))continue;
 for(const s of penpotUtils.findShapes(s=>!s.children?.length,b)){
  if(s.name==='个性化Mod生成器'||s.name==='Baldur’s Gate 3 标志')continue;
  if(s.y-b.y>=196)s.y+=80;
 }
 b.setPluginData('body-shifted','80');
}
for(const b of Object.values(B))for(const s of penpotUtils.findShapes(s=>s.type==='text'&&s.characters==='个性化Mod生成器',b))s.x=b.x+(b.width-s.width)/2;
// Overlay tabs use the visible capsule bounds, not text-only hit areas.
for(const [name,label,x] of [['弹窗-A-装备选择','技能标签',148],['弹窗-B-技能选择','装备标签',32]]){
 const b=B[name],s=penpotUtils.findShape(s=>s.name==='点击-'+label,b);s.x=b.x+x;s.y=b.y+112;s.resize(112,36);
}
// A close or cancel always returns to the initiating home without stacked selectors.
for(const name of ['弹窗-A-装备选择','弹窗-B-技能选择']){
 const b=B[name];for(const label of ['取消','关闭']){const s=penpotUtils.findShape(s=>s.name==='点击-'+label,b);s.interactions.forEach(i=>s.removeInteraction(i));s.addInteraction('click',{type:'navigate-to',destination:B['01-问答首页']});}
}
return {shifted:true};
