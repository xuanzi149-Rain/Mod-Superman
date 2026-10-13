const $ = id => document.getElementById(id);
const names = {damage:'基础伤害',versatile_damage:'双手伤害',name:'中文名称',weight_kg:'重量（kg）',rarity:'稀有度'};
const originalKeys = {damage:'Damage',versatile_damage:'VersatileDamage',weight_kg:'Weight',rarity:'Rarity'};
let session = null, busy = false, dirty = false;
function status(text, error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
async function api(path, body){
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail?.message || (Array.isArray(data.detail)?data.detail.map(x=>x.msg).join('；'):JSON.stringify(data.detail)));
  return data;
}
function gate(){
  $('send').disabled=busy||!session||dirty;
  $('save').disabled=busy||!session;
  $('preview').disabled=busy||!session||dirty||!Object.keys(session.draft).length||session.questions.length>0||session.unsupported.length>0;
  $('choose').disabled=busy||!$('equipment').value;
  const p=session?.preview;
  $('confirmed').disabled=busy||!p||dirty;
  $('generate').disabled=busy||!p||p.status==='succeeded'||dirty||!$('confirmed').checked||(p.experimental&&!$('experimental').checked);
  document.querySelectorAll('#fields input,#fields select').forEach(x=>x.disabled=busy);
}
async function run(action){
  if(busy)return;busy=true;gate();status('正在处理，请稍候…');
  try{await action();status('已完成，请核对结果。');}
  catch(e){
    if(session){try{session=await api('/api/ai/sessions/'+session.session_id);if(!dirty)render();}catch{}}
    status(e.message,true);
  }finally{busy=false;gate();}
}
function requestBody(extra={}){return {version:session.version,request_id:crypto.randomUUID(),...extra};}
function render(){
  if(!session)return;
  if([...$('equipment').options].some(option=>option.value===session.object))$('equipment').value=session.object;
  $('object-info').textContent=session.detail.display_name+' · 可修改：'+Object.keys(session.detail.field_rules).map(k=>names[k]).join('、')+' · 草稿版本 '+session.version;
  $('chat').replaceChildren();
  for(const event of session.history){
    for(const [role,text] of [['user',event.text||(event.kind==='manual'?'已提交完整手动参数':'' )],['assistant',event.error?.message||event.interpretation?.explanation]]){
      if(!text)continue;const el=document.createElement('div');el.className='turn '+role;
      const title=document.createElement('strong');title.textContent=role==='user'?'你':'解析结果';el.append(title,document.createTextNode(text));$('chat').append(el);
    }
  }
  $('chat').scrollTop=$('chat').scrollHeight;
  $('fields').replaceChildren();
  for(const [field,rule] of Object.entries(session.detail.field_rules)){
    const row=document.createElement('tr');row.dataset.field=field;
    const selected=document.createElement('input');selected.type='checkbox';selected.checked=Object.hasOwn(session.draft,field);selected.setAttribute('aria-label','修改'+names[field]);
    const original=field==='name'?session.detail.display_name:session.detail.original[originalKeys[field]];
    const editor=document.createElement(rule.type==='enum'?'select':'input');editor.setAttribute('aria-label',names[field]+'新值');
    if(rule.type==='enum'){for(const value of rule.values){const o=document.createElement('option');o.value=value;o.textContent=value;editor.append(o);}}
    else{editor.type=field==='weight_kg'?'number':'text';if(field==='weight_kg'){editor.step='.001';editor.min='0';editor.max='100';}}
    editor.value=session.draft[field]??original??'';
    for(const value of [selected,names[field],String(original??'未知'),editor]){const cell=document.createElement('td');cell.append(value instanceof Node?value:document.createTextNode(value));row.append(cell);}
    for(const input of [selected,editor])input.addEventListener('input',()=>{dirty=true;$('confirmed').checked=false;$('download').hidden=true;gate();status('表格有未保存修改。请先保存手动参数，再创建新预览。');});
    $('fields').append(row);
  }
  const pending=[...session.questions.map(x=>'待澄清：'+x),...session.unsupported.map(x=>'不支持：'+x)];
  $('pending').hidden=!pending.length;$('pending').textContent=pending.join('\n');
  $('supported-label').hidden=!session.unsupported.length;$('supported').checked=false;
  const operationNames={set:'设为',remove:'撤销修改',add:'增加',subtract:'减少',multiply:'乘以'};
  $('trace').textContent=[session.explanation,...session.trace.map(op=>`${names[op.field]}：${operationNames[op.operation]} ${op.value??''}${op.unit??''}\n计算基准：${op.basis==='original'?'目录原值':'当前草稿（无草稿时用原值）'} ${op.base??'未知'}\n结果：${op.new??'未知'}；校验：${op.check}`)].join('\n\n')||'尚无修改操作。';
  const p=session.preview;$('preview-info').hidden=!p;
  $('preview-info').textContent=p?['方案 '+p.plan_id,...p.changes.map(x=>names[x.field]+'：'+x.original+' → '+x.new),'影响范围：数值覆盖会影响共用此记录的装备，并可能影响继承记录；不能保证只修改背包中的单个实例。',p.experimental?'本方案含未验证参数或组合，需要接受试验提示。':'存在历史参考方案，但本次新包仍须独立验证。',p.status==='succeeded'?'源文件、PAK 和 ZIP 检查已通过。':'等待独立确认后生成。','本包游戏验证：未执行'].join('\n'):'';
  $('confirmed').checked=false;$('experimental').checked=false;$('experimental-label').hidden=!p?.experimental;$('download').hidden=true;
  if(p?.status==='succeeded'){$('download').href=p.download_url;$('download').hidden=false;}
  dirty=false;gate();
}
async function search(){const data=await api('/api/equipment?limit=100&search='+encodeURIComponent($('search').value));$('equipment').replaceChildren();for(const item of data.items){const o=document.createElement('option');o.value=item.object_id;o.textContent=item.display_name+' · '+item.category+' · '+item.object_id.slice(-8);$('equipment').append(o);}$('search-info').textContent=`共 ${data.total} 个候选，显示前 ${data.items.length} 个；可缩小名称搜索。候选不代表已游戏验证。`;}
$('search-form').addEventListener('submit',e=>{e.preventDefault();run(search);});
$('choose').addEventListener('click',()=>run(async()=>{session=await api('/api/ai/sessions',{object:$('equipment').value});sessionStorage.setItem('mod-superman-session',session.session_id);render();}));
$('message-form').addEventListener('submit',e=>{e.preventDefault();if(!$('message').value.trim())return;run(async()=>{session=await api('/api/ai/sessions/'+session.session_id+'/messages',requestBody({text:$('message').value}));$('message').value='';render();});});
$('save').addEventListener('click',()=>run(async()=>{const changes={};for(const row of $('fields').rows){if(!row.cells[0].firstChild.checked)continue;const field=row.dataset.field;const value=row.cells[3].firstChild.value;if(field==='weight_kg'&&value.trim()==='')throw new Error('请填写重量。');changes[field]=field==='weight_kg'?Number(value):value;}session=await api('/api/ai/sessions/'+session.session_id+'/draft',requestBody({changes,accept_supported_only:$('supported').checked}));render();}));
$('preview').addEventListener('click',()=>run(async()=>{session=await api('/api/ai/sessions/'+session.session_id+'/preview',requestBody());render();}));
for(const id of ['confirmed','experimental'])$(id).addEventListener('change',gate);
$('generate').addEventListener('click',()=>run(async()=>{session.preview=await api('/api/plans/'+session.preview.plan_id+'/generate',{confirmed:$('confirmed').checked,accept_experimental:$('experimental').checked});render();}));
run(async()=>{await search();const id=sessionStorage.getItem('mod-superman-session');if(id){try{session=await api('/api/ai/sessions/'+id);render();}catch{sessionStorage.removeItem('mod-superman-session');}}});
