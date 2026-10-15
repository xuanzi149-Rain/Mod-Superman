storage.boards=storage.boards||{};
storage.font=penpot.fonts.findByName('Noto Sans SC');
if(!storage.font)throw Error('Noto Sans SC is unavailable');
storage.importBoard=async function(d){
 if(storage.boards[d.name])return storage.boards[d.name];
 const b=penpot.createBoard();b.name=d.name;b.resize(d.w,d.h);b.x=d.x;b.y=d.y;b.fills=[{fillColor:'#FFFFFF',fillOpacity:1}];b.clipContent=true;b.showInViewMode=d.kind!=='overlay';
 storage.boards[d.name]=b;
 const g=penpot.createShapeFromSvg(d.svg);if(!g)throw Error('SVG import failed: '+d.name);
 b.appendChild(g);g.name='图形与背景';g.x=d.x;g.y=d.y;
 for(const p of d.images){const im=storage.logo.clone();b.appendChild(im);im.name='Baldur’s Gate 3 标志';im.resize(p.w,p.h);im.x=d.x+p.x;im.y=d.y+p.y;}
 const native=[];
 for(const t of d.texts){const s=penpot.createText(t.text);b.appendChild(s);s.name=t.text;storage.font.applyToText(s,storage.font.variants.find(v=>v.fontWeight===t.weight));s.fontSize=String(t.size);s.fontWeight=t.weight;s.growType='auto-width';s.fills=[{fillColor:t.color,fillOpacity:1}];s.strokes=[];s.x=d.x+t.x;s.y=d.y+t.y;native.push([s,t]);}
 for(const [s,t] of native){if(t.anchor==='middle')s.x=d.x+t.x-s.width/2;}
 for(const h of d.hotspots){const s=penpot.createRectangle();b.appendChild(s);s.name='点击-'+h.label;s.resize(h.w,h.h);s.x=d.x+h.x;s.y=d.y+h.y;s.fills=[{fillColor:'#FFFFFF',fillOpacity:0}];s.strokes=[];}
 return b;
};
penpot.currentPage.name='Mod-Superman · 问答原型';
