const {test}=require('node:test');
const assert=require('node:assert/strict');
const M=require('./model.js');
for(const [object,question,expected] of [
 ['sword','把基础伤害骰数量翻倍，保留其他效果。','2d6'],
 ['sword','基础伤害改为3d6','3d6'],
 ['sword','把中文名称改为曙光短剑，保留其他效果。','曙光短剑'],
 ['heal','把治愈真言施法距离改为36米。','36']
])test(`${object}: ${expected} survives confirmation and result`,()=>{
 const s=M.create(),r=M.parse(object,question);assert.ok(r.plan);
 M.setPlan(s,r.plan);assert.throws(()=>M.generate(s),/confirmation/);
 M.confirm(s);M.generate(s);assert.equal(s.step,3);assert.equal(s.result.value,expected);assert.equal(s.result.object,object);
});
test('changing 2d6 to 3d6 invalidates confirmation and old result',()=>{
 const s=M.create();M.setPlan(s,M.parse('sword','伤害翻倍').plan);M.confirm(s);M.generate(s);
 M.setPlan(s,{...s.plan,value:'3d6'});assert.equal(s.confirmed,null);assert.equal(s.result,null);
 assert.throws(()=>M.generate(s));M.confirm(s);M.generate(s);assert.equal(s.result.value,'3d6');
});
test('even a direct mutation cannot reuse stale confirmation',()=>{
 const s=M.create();M.setPlan(s,M.parse('sword','伤害翻倍').plan);M.confirm(s);s.plan.value='3d6';assert.throws(()=>M.generate(s));
});
test('invalid or ambiguous requests do not create plans',()=>{
 for(const q of ['', '变得强一点','伤害改为20d6','所有属性翻倍','价格设为100'])assert.equal(M.parse('sword',q).plan,undefined);
 assert.equal(M.parse('heal','距离改为100米').plan,undefined);
});
test('switching objects cannot reuse sword dice on skill',()=>{
 assert.equal(M.parse('heal','基础伤害改为2d6').plan,undefined);
 assert.equal(M.parse('sword','施法距离改为36米').plan,undefined);
});
test('new modification starts clean',()=>{const s=M.create();assert.equal(s.plan,null);assert.equal(s.result,null);assert.equal(s.feedback,null);assert.equal(s.step,1);});

test('multiple fields survive one confirmation and generation',()=>{
 const s=M.create();M.setPlan(s,M.parse('sword','伤害翻倍').plan);
 const plan=M.changePlan(s.plan,[...M.rows(s.plan),{field:'name',value:'曙光短剑'},{field:'weight_kg',value:'0.45'},{field:'rarity',value:'Rare'}]);
 M.setPlan(s,plan);M.confirm(s);assert.equal(s.step,2);M.generate(s);
 assert.equal(s.step,3);assert.deepEqual(M.rows(s.result).map(x=>x.value),['2d6','曙光短剑','0.45','Rare']);
 s.plan.changes[1].value='新名称';assert.equal(s.result.changes[1].value,'曙光短剑');assert.throws(()=>M.generate(s));
});
test('adding parameters invalidates old confirmation',()=>{
 const s=M.create();M.setPlan(s,M.parse('sword','伤害翻倍').plan);M.confirm(s);
 M.setPlan(s,M.changePlan(s.plan,[...M.rows(s.plan),{field:'name',value:'曙光短剑'}]));assert.equal(s.confirmed,null);assert.throws(()=>M.generate(s));
});
test('available fields enforce object capabilities, uniqueness and ranges',()=>{
 const p=M.parse('sword','伤害翻倍').plan;
 for(const c of [[{field:'versatile_damage',value:'2d6'}],[{field:'damage',value:'2d6'},{field:'damage',value:'3d6'}],[{field:'weight_kg',value:'101'}],[{field:'rarity',value:'invalid'}],[]])assert.throws(()=>M.changePlan(p,c));
 assert.equal(M.changePlan(p,[{field:'weight_kg',value:'0'}]).changes[0].old,'0.9');
 assert.throws(()=>M.changePlan(M.parse('heal','距离改为36米').plan,[{field:'name',value:'test'}]));
});
