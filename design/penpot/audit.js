const B=storage.boards;
const report=[];
for(const [name,b] of Object.entries(B)){
 const text=penpotUtils.findShapes(s=>s.type==='text',b);
 const targets=penpotUtils.findShapes(s=>s.interactions?.length>0,b).map(s=>({button:s.name,actions:s.interactions.map(i=>({trigger:i.trigger,type:i.action.type,target:i.action.destination?.name,delay:i.delay}))}));
 const invalid=targets.flatMap(s=>s.actions.filter(i=>['navigate-to','open-overlay'].includes(i.type)&&!i.target));
 report.push({name,id:b.id,texts:text.length,targets,invalid});
}
return {fileId:penpot.currentFile.id,pageId:penpot.currentPage.id,report};
