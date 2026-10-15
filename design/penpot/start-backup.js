storage.backup={status:'exporting'};
penpot.currentFile.export('penpot','detach').then(bytes=>{
 let str='';for(let i=0;i<bytes.length;i+=8192)str+=String.fromCharCode(...bytes.slice(i,i+8192));
 storage.backup={status:'ready',base64:btoa(str),bytes:bytes.length};
}).catch(e=>{storage.backup={status:'failed',error:String(e)};});
return {status:storage.backup.status};
