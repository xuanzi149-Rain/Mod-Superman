const fonts=penpot.fonts.all.filter(f=>/Noto Sans SC|Source Han|Chinese/.test(f.name));
storage.probe=penpot.createShapeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="360" height="100"><rect width="360" height="100" fill="#FFFFFF"/><text x="20" y="60" font-family="Noto Sans SC" font-size="28">个性化Mod生成器</text></svg>');
storage.probe.name='迁移测试-中文可编辑性';
return {fonts:fonts.map(f=>({id:f.id,name:f.name})), structure:penpotUtils.shapeStructure(storage.probe,3)};
