const B=storage.boards;
const issues=[];
const shapes=b=>penpotUtils.findShapes(()=>true,b);
const check=(name,label,target)=>{
 const s=shapes(B[name]).find(s=>s.name==='点击-'+label);
 if(!s?.interactions.some(i=>i.action.destination?.id===B[target].id))issues.push(name+' / '+label+' target mismatch');
};
check('02-参数编辑','重新确认参数','03-确认3d6');check('03-确认3d6','生成修改文件','03-生成3d6');
check('技能-结果','确认参数','技能-确认');check('技能-确认','生成修改文件','04-技能下载');
check('02-中文名结果','确认参数','03-中文名确认');check('03-中文名确认','生成修改文件','04-中文名下载');
check('反馈-DEMO-SWORD-3D6','取消','04-结果3d6');check('反馈-DEMO-HEAL-36','取消','04-技能下载');
const all=shapes(penpot.root),interactive=all.filter(s=>s.interactions?.length),texts=all.filter(s=>s.type==='text'&&!s.hidden);
for(const s of interactive)for(const i of s.interactions)if(['navigate-to','open-overlay'].includes(i.action.type)&&!i.action.destination)issues.push('Missing target '+s.name);
const badFonts=texts.filter(t=>t.fontFamily!=='Noto Sans SC').map(t=>t.name);
const b=B['01-问答首页'];penpot.selection=[b];penpot.viewport.zoomIntoView([b]);
return {fileId:penpot.currentFile.id,pageId:penpot.currentPage.id,boards:Object.keys(B).length,textLayers:texts.length,interactions:interactive.reduce((sum,s)=>sum+s.interactions.length,0),flows:penpot.currentPage.flows.map(f=>f.name),issues,badFonts,validation:'连接数据和参数分支一致性检查；没有执行真人点击测试'};
