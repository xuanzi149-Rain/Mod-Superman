/* Fixed prototype examples; no model requests or production validation. */
(function(root){
'use strict';
const objects={sword:{name:'第一滴血短剑',type:'装备'},heal:{name:'治愈真言',type:'技能'}};
// Snapshot: data/equipment_catalog.json, first-blood template capabilities/original.
const fields={sword:{damage:{kind:'dice',label:'基础伤害',old:'1d6'},name:{kind:'name',label:'中文名称',old:'第一滴血短剑'},weight_kg:{kind:'weight',label:'重量（kg）',old:'0.9'},rarity:{kind:'rarity',label:'稀有度',old:'Uncommon'}},heal:{cast_distance_m:{kind:'distance',label:'施法距离（米）',old:'18'}}};
const rarities={Common:'普通',Uncommon:'精良',Rare:'稀有',VeryRare:'珍奇',Legendary:'传奇'};
function rows(plan){return plan.changes||[{field:({dice:'damage',name:'name',distance:'cast_distance_m'})[plan.kind],kind:plan.kind,label:plan.label,old:plan.old,value:plan.value}];}
function validate(kind,value){
 if(kind==='dice'&&!/^(?:[1-9]|10)d(?:4|6|8|10|12|20)$/.test(value))return '请使用 NdS 格式：骰数 1～10，骰面为 4、6、8、10、12 或 20。';
 if(kind==='distance'&&(!/^\d+(?:\.\d)?$/.test(value)||+value<1||+value>60))return '请输入 1～60 米，最多一位小数。';
 if(kind==='name'&&(!value.trim()||value.length>60||/[\u0000-\u001f]/.test(value)))return '名称需为 1～60 个字符，不含控制字符。';
 if(kind==='weight'&&(!/^\d+(?:\.\d{1,3})?$/.test(value)||+value>100))return '重量需为 0～100 kg，最多三位小数。';
 if(kind==='rarity'&&!Object.hasOwn(rarities,value))return '请选择有效的稀有度。';
 return '';
}
function parse(object,q){
 q=q.trim();if(!q)return {error:'请先输入修改期望。'};
 if(/无限|全部|所有|攻击速度|价格|稀有度|重量/.test(q))return {error:'当前交互原型仅演示基础伤害、中文名称和治愈真言距离，请选择下方示例或重新描述。',type:'unsupported'};
 let plan;
 if(object==='heal'){
   const m=q.match(/(\d+(?:\.\d+)?)\s*米/);
   if(m&&/距离|射程|米/.test(q))plan={kind:'distance',label:'施法距离（米）',old:'18',value:m[1]};
 }else if(/名称|名字|中文名|改名/.test(q)){
   const m=q.match(/(?:改为|改成|叫做|叫)[「“"']?([^」”"'，。\n]+)/);
   if(m)plan={kind:'name',label:'中文名称',old:objects.sword.name,value:m[1].trim()};
 }else if(/伤害|\d+d\d+/.test(q)){
   const m=q.match(/\d+d\d+/i);
   if(m||/翻倍/.test(q))plan={kind:'dice',label:'基础伤害',old:'1d6',value:m?m[0].toLowerCase():'2d6'};
 }
 if(!plan)return {error:object==='heal'?'请补充目标施法距离，例如“施法距离改为36米”。':'请补充具体字段与目标值，例如“基础伤害改为3d6”或“中文名称改为曙光短剑”。',type:'clarify'};
 const error=validate(plan.kind,plan.value);return error?{error,type:'invalid'}:{plan:{...plan,object,question:q}};
}
function create(){return {step:1,object:'sword',plan:null,confirmed:null,result:null,draft:'',busy:false,feedback:null};}
function setPlan(s,plan){s.plan=JSON.parse(JSON.stringify(plan));s.object=plan.object;s.confirmed=null;s.result=null;s.feedback=null;s.step=2;}
function changePlan(plan,changes){
 if(!changes.length)throw Error('请至少保留一个修改参数。');
 const used=new Set();const normalized=changes.map(c=>{const rule=fields[plan.object]?.[c.field];if(!rule||used.has(c.field))throw Error('参数不支持或已重复添加。');used.add(c.field);const value=String(c.value).trim();const err=validate(rule.kind,value);if(err)throw Error(rule.label+'：'+err);return {field:c.field,...rule,value};});
 return {...plan,...normalized[0],changes:normalized};
}
function confirm(s){if(!s.plan)throw Error('invalid plan');changePlan(s.plan,rows(s.plan));s.confirmed=JSON.stringify(s.plan);s.step=2;}
function generate(s){if(s.confirmed!==JSON.stringify(s.plan)||!s.plan)throw Error('confirmation required');s.result=JSON.parse(JSON.stringify(s.plan));s.feedback=null;s.step=3;}
const api={objects,fields,rarities,rows,changePlan,validate,parse,create,setPlan,confirm,generate};root.PrototypeModel=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
