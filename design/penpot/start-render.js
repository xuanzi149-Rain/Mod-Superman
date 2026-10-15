storage.renders=storage.renders||{};
for(const name of ['01-问答首页','02-问答结果','04-结果下载页','02-参数编辑','技能-结果','反馈-DEMO-HEAL-36']){
 storage.renders[name]={status:'exporting'};
 storage.boards[name].export({type:'png'}).then(bytes=>{let str='';for(let i=0;i<bytes.length;i+=8192)str+=String.fromCharCode(...bytes.slice(i,i+8192));storage.renders[name]={status:'ready',base64:btoa(str),bytes:bytes.length};}).catch(e=>storage.renders[name]={status:'failed',error:String(e)});
}
storage.backup={status:'exporting'};
penpot.currentFile.export('zip','all').then(bytes=>{let str='';for(let i=0;i<bytes.length;i+=8192)str+=String.fromCharCode(...bytes.slice(i,i+8192));storage.backup={status:'ready',base64:btoa(str),bytes:bytes.length};}).catch(e=>storage.backup={status:'failed',error:String(e)});
return {status:'started'};
