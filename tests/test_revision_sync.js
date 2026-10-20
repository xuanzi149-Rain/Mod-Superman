const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('web/craft.js','utf8');
const input={value:'可以改哪些参数'};
const ctx={state:null,$:()=>input,notice(){},render(){input.value='';}};
vm.createContext(ctx);vm.runInContext(src.slice(src.indexOf('async function submitAction('),src.indexOf('async function action(')),ctx);
const stale=()=>Object.assign(Error('old revision'),{code:'stale_revision'});
(async()=>{
 for(const name of ['message','generate','edit']){
 ctx.state={session_id:'s',revision:1,plan:{name:'原装备'}};let calls=[];
 ctx.api=async(path,body)=>{calls.push({path,body});if(calls.length===1)throw stale();if(!body)return {session_id:'s',revision:2,plan:{name:'原装备'}};return {assistant_response:'可以修改重量等参数。'};};
 const request={revision:1,request_id:'once',data:{text:input.value}};
 if(name==='message'){
 const result=await ctx.submitAction(name,request);assert.match(result.assistant_response,/重量/);assert.equal(calls.length,3);assert.equal(calls[2].body.revision,2);assert.equal(calls[2].body.request_id,'once');
 }else{await assert.rejects(ctx.submitAction(name,request),/尚未执行/);assert.equal(calls.length,2);}
 assert.equal(input.value,'可以改哪些参数');
 }
 ctx.state={session_id:'s',revision:1,plan:{name:'旧'}};let n=0;
 ctx.api=async()=>{if(++n===1)throw stale();return {session_id:'s',revision:3,plan:{name:'新'}};};
 await assert.rejects(ctx.submitAction('message',{revision:1}),/尚未执行/);assert.equal(n,2);assert.equal(ctx.state.plan.name,'新');assert.equal(input.value,'可以改哪些参数');
 ctx.state={session_id:'s',revision:1,plan:{}};n=0;
 ctx.api=async(path,body)=>{n++;if(body)throw stale();return {session_id:'s',revision:2,plan:{}};};
 await assert.rejects(ctx.submitAction('message',{revision:1}),/再次发生变化/);assert.equal(n,3);
 console.log('Revision sync: unchanged-plan retry, changed-plan preservation, no generate/edit replay, bounded retry passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
