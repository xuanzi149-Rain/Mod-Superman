storage.localBackup={status:'exporting'};
penpot.currentFile.export().then(bytes=>{let str='';for(let i=0;i<bytes.length;i+=8192)str+=String.fromCharCode(...bytes.slice(i,i+8192));storage.localBackup={status:'ready',base64:btoa(str),bytes:bytes.length};}).catch(e=>storage.localBackup={status:'failed',error:String(e)});
return {started:true};
