const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('web/craft.js','utf8').split('async function preparePreview(){')[1];
const nodes={},calls=[];
function node(){return {value:'保留输入',innerHTML:'',focus(){},scrollIntoView(){},remove(){},append(x){nodes['#preview-blockers']=x;}};}
const ctx={busy:false,state:{issues:[{id:'bad',detail:'无效要求'}],validation:['unresolved_questions'],texts:[]},inputFeedback:{},esc:String,friendly:String,document:{createElement:node},$:key=>nodes[key]||(nodes[key]=node()),clearError:()=>calls.push('clear'),notice:t=>calls.push(t),edit:async(a,b,data)=>{assert.equal(data.withdraw[0],'bad');ctx.state.issues=[];ctx.state.validation=[];return ctx.state;},action:async(name,data,opts)=>{calls.push(name);if(name==='preview')assert.equal(opts.next,true);return ctx.state;}};
vm.createContext(ctx);vm.runInContext('async function preparePreview(){'+source,ctx);
(async()=>{
 await ctx.preparePreview();assert.ok(nodes['#preview-blockers'].innerHTML.includes('无效要求'));assert.ok(!calls.includes('preview'));
 await nodes['#keep-applied'].onclick();assert.ok(calls.includes('preview'));assert.equal(ctx.inputFeedback,null);
 calls.length=0;ctx.state.validation=['empty_changes'];await ctx.preparePreview();assert.ok(!calls.includes('preview'));assert.ok(nodes['#preview-blockers'].innerHTML.includes('empty_changes'));
 calls.length=0;ctx.state.validation=[];await ctx.preparePreview();assert.ok(calls.includes('preview'));assert.ok(calls.includes('clear'));
 assert.ok(!fs.readFileSync('web/craft.js','utf8').includes('请先完成「继续前还需完成」'));
 console.log('Preview recovery: explicit withdrawal, valid continuation, invalid-plan blocking and stale error clearing passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
