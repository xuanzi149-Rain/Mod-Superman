const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const code=fs.readFileSync('web/craft.js','utf8');
const feedback=require('../web/craft-feedback.js');
const nodes={'#prompt':{value:'问题原文'},'#editor':{open:false}};
const ctx={busy:false,state:{session_id:'s',revision:1,issues:[]},inputFeedback:null,step:1,crypto:{randomUUID:()=> 'r'},$:k=>nodes[k],clearError(){},setBusy(){},notice(){},localStorage:{setItem(){}},CraftFeedback:feedback,render(){nodes['#prompt'].value='';},fail(m){throw Error(m);}};
vm.createContext(ctx);vm.runInContext(code.slice(code.indexOf('async function action('),code.indexOf('\nconst op=')),ctx);
(async()=>{
 for(const response of [
 {input_retained:true,input_feedback:[{detail:'能力尚未实现'}]},
 {operation_result:{before:{},after:{}}},
 {input_retained:true,assistant_response:'会保留未提及的效果。'}]){
 ctx.submitAction=async()=>({session_id:'s',revision:1,issues:[],texts:[],...response});
 await ctx.action('message',{text:'问题原文'});
 assert.equal(nodes['#prompt'].value,'问题原文');
 }
 assert.equal(ctx.inputFeedback.rows.length,0);
 assert.equal(ctx.inputFeedback.reply,'会保留未提及的效果。');
 console.log('Input retention: failure, legacy no-op and answer passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
