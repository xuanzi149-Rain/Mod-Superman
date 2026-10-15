storage.boards=Object.fromEntries(penpot.root.children.filter(s=>s.type==='board').map(s=>[s.name,s]));
storage.font=penpot.fonts.findByName('Noto Sans SC');
return {file:penpot.currentFile.name,page:penpot.currentPage.name,boards:Object.keys(storage.boards).length};
