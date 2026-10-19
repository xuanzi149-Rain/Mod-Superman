const {test}=require('node:test');
const assert=require('node:assert/strict');
const {preparation}=require('./craft-feedback.js');
const {validationReason}=require('./craft-feedback.js');

test('weight precision failure has a concrete recovery path',()=>{
  const text=validationReason('parameters.weight_kg:three_decimals_max');
  assert.match(text,/三位小数/);assert.match(text,/尚未应用/);assert.match(text,/明确/);
});
test('pending requirement is not misreported as missing user input',()=>{
  assert.deepEqual(preparation({texts:[],issues:[{id:'q'}],validation:['empty_changes','unresolved_questions']}),[]);
});
test('found resource with unreviewed mechanics does not ask for already supplied details',()=>{
  const message=validationReason('effects.test:STUNNED:unreviewed_function:AbilityFailedSavingThrow');
  assert.match(message,/已找到/);assert.match(message,/无需重复/);assert.ok(!message.includes('STUNNED'));
});
test('reported rename scenario groups visual failures and preserves pending name',()=>{
  const rows=preparation({texts:[{target:{owner:'equipment',field:'name'},text:'新名字'}],validation:[
    'base_equipment:unqualified_visual','display.name:required_for_new_equipment',
    'acquisition:unknown_or_unverified','base_equipment:skeleton_mapping_not_reviewed',
    'base_equipment:visual_model_not_verified','unresolved_questions']});
  assert.deepEqual(rows.map(x=>x.key),['base','acquisition','pending-name']);
  assert.match(rows[2].message,/新名字.*已保存/);
  assert.ok(!JSON.stringify(rows).includes('skeleton_mapping'));
  assert.equal(rows.filter(x=>x.blocked).length,1);
});
test('unfinished creation fields are preparation, not three technical errors',()=>{
  const rows=preparation({texts:[],validation:['display.name:required_for_new_equipment','acquisition:unknown_or_unverified']});
  assert.equal(rows.length,2);assert.ok(rows.every(x=>!x.blocked&&x.action));
});
test('unknown capability failures are still visible and blocking',()=>{
  const rows=preparation({texts:[],validation:['effects.test:unexpected_mechanism']});
  assert.equal(rows[0].blocked,true);assert.equal(rows[0].action,'prompt');
});
const {latestInput}=require('./craft-feedback.js');
test('latest feedback excludes unchanged historical issues',()=>{
 const old={id:'old_q',detail:'旧问题'};
 const current={issues:[old,{id:'new_q',detail:'缺少数值',question:'请填写目标重量'}],last_result:{before:{x:1},after:{x:1}}};
 assert.deepEqual(latestInput({issues:[old]},current,'new'),[{reason:'缺少数值',solution:'请填写目标重量'}]);
});
test('successful new input does not repeat old warnings',()=>{
 const old={id:'old_q',detail:'旧问题'};
 assert.deepEqual(latestInput({issues:[old]},{issues:[old],last_result:{before:{x:1},after:{x:2}}},'next'),[]);
});
test('no useful change explains how to retry',()=>{
 const rows=latestInput({issues:[]},{issues:[],texts:[],last_result:{before:{},after:{}}},'empty');
 assert.equal(rows.length,1);assert.match(rows[0].solution,/重量改为/);
});
