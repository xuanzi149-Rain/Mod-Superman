const version=await penpot.currentFile.saveVersion('Mod-Superman · 原型连接完成 · 2026-10-13');
return {saved:true,fileId:penpot.currentFile.id,pageId:penpot.currentPage.id,versionId:version.id,label:version.label};
