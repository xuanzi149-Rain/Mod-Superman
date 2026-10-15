storage.alignmentRenders={};
for(const name of ['02-中文名结果','01-问答首页']){
 storage.alignmentRenders[name]={status:'exporting'};
 storage.boards[name].export({type:'png'}).then(bytes=>{let str='';for(let i=0;i<bytes.length;i+=8192)str+=String.fromCharCode(...bytes.slice(i,i+8192));storage.alignmentRenders[name]={status:'ready',base64:btoa(str),bytes:bytes.length};}).catch(e=>storage.alignmentRenders[name]={status:'failed',error:String(e)});
}
return {started:true};
