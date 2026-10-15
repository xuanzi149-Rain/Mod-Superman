const name='02-问答结果';storage.revisionRenders[name]={status:'exporting'};
storage.boards[name].export({type:'png'}).then(bytes=>{let str='';for(let i=0;i<bytes.length;i+=8192)str+=String.fromCharCode(...bytes.slice(i,i+8192));storage.revisionRenders[name]={status:'ready',base64:btoa(str),bytes:bytes.length};}).catch(e=>storage.revisionRenders[name]={status:'failed',error:String(e)});
return {started:true};
