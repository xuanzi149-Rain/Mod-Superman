const B=storage.boards;
const star=penpotUtils.findShape(s=>s.type==='path'&&s.x-B['01-问答首页'].x>70&&s.x-B['01-问答首页'].x<85&&s.y-B['01-问答首页'].y<40&&s.width<24,B['01-问答首页']);
for(const b of Object.values(B)){
 if(b.width!==1440)continue;
 const logo=penpotUtils.findShape(s=>s.name==='Baldur’s Gate 3 标志',b);if(logo){logo.resize(165,107.38);logo.x=b.x+637.5;logo.y=b.y+96;}
 const matching=penpotUtils.findShape(s=>s.type==='path'&&s.x-b.x>70&&s.x-b.x<85&&s.y-b.y<40&&s.width<24,b);
 if(star&&!matching){const s=star.clone();b.appendChild(s);s.x=b.x+star.x-B['01-问答首页'].x;s.y=b.y+star.y-B['01-问答首页'].y;s.name='页头白色标志';}
}
for(const name of ['技能-结果','技能-确认']){
 const b=B[name],s=penpot.createRectangle();b.appendChild(s);s.name='点击-发送调整';s.resize(46,46);s.x=b.x+1087;s.y=b.y+788;s.fills=[{fillColor:'#FFFFFF',fillOpacity:0}];s.strokes=[];s.addInteraction('click',{type:'navigate-to',destination:B['01-治愈真言']});
}
const t=penpotUtils.findShape(s=>s.type==='text'&&s.characters==='↗ 改一个技能名称',B['01-治愈真言']);if(t)t.characters='↗ 改一个装备名称';
return {headerStar:!!star};
