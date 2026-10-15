/* Three-page MVP: rendering is separate from the server-owned workflow. */
(()=>{'use strict';
const $=id=>document.getElementById(id), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={damage:'基础伤害',versatile_damage:'双手伤害',name:'中文名称',weight_kg:'重量（kg）',rarity:'稀有度'};
const keys={damage:'Damage',versatile_damage:'VersatileDamage',weight_kg:'Weight',rarity:'Rarity'};
const rarities={Common:'普通',Uncommon:'精良',Rare:'稀有',VeryRare:'珍奇',Legendary:'传奇'};
let session=null,step=1,working=false,input='',plan=null,focusBefore=null,pollTimer=null,pickerSerial=0;
const storage={get(k){try{return JSON.parse(localStorage.getItem('mod-live-'+k));}catch{return null;}},set(k,v){try{localStorage.setItem('mod-live-'+k,JSON.stringify(v));}catch{}}};
input=storage.get('input')||'';
async function api(path,body){
 let response;try{response=await fetch(path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}catch{throw Object.assign(Error('网络连接中断。输入已保留，请重试或刷新恢复状态。'),{network:true});}
 let data;try{data=await response.json();}catch{throw Object.assign(Error('服务器响应中断，请查询状态或重试。'),{network:true});}
 if(!response.ok){const d=data.detail;throw Object.assign(Error(d?.message||(Array.isArray(d)?d.map(x=>x.msg).join('；'):'请求失败，请稍后重试。')),{code:d?.code,status:response.status});}return data;
}
function body(extra={}){return {version:session.version,request_id:crypto.randomUUID(),...extra};}
function button(id,label,primary=false){return `<button id="${id}" class="${primary?'primary':'secondary'}">${label}</button>`;}
function bind(id,fn){if($(id))$(id).onclick=fn;}
function err(message,id='error'){const el=$(id);if(el){el.textContent=message;el.focus();}}
function errorBox(id='error'){return `<div id="${id}" class="error" role="alert" tabindex="-1"></div>`;}
function note(title,text){return `<section class="note"><h4>${esc(title)}</h4><p>${text}</p></section>`;}
function original(field){return field==='name'?session.detail.display_name:session.detail.original[keys[field]];}
function display(field,value){return field==='rarity'?(rarities[value]||value):String(value??'未知');}
function rows(){return plan?.changes||Object.entries(session?.draft||{}).map(([field,value])=>({field,original:original(field),new:value}));}
function summary(){return rows().map(r=>`${esc(labels[r.field])}：${esc(display(r.field,r.original))} → ${esc(display(r.field,r.new))}`).join('<br>');}
function move(n){step=n;history.pushState({step:n},'',`#step-${n}`);render();$('heading').focus();}
function modal(title,html){focusBefore=document.activeElement;$('dialog-title').textContent=title;$('dialog-body').innerHTML=html;if(!$('dialog').open)$('dialog').showModal();}
function close(){ $('dialog').close(); }
$('close-dialog').onclick=close;
$('dialog').addEventListener('close',()=>{if(focusBefore?.isConnected)focusBefore.focus();else $('heading').focus();});
function render(){
 const name=session?.detail.display_name||'请选择装备';
 $('heading').innerHTML=[['生成你的','私人定制Mod！'],['确认参数'],['修改已就绪','带进你的游戏。']][step-1].map(x=>`<span>${x}</span>`).join('');
 $('steps').innerHTML=['描述','确认','下载'].map((x,i)=>`<li class="${i===step-1?'active':''}" ${i===step-1?'aria-current="step"':''}><b>0${i+1}</b><span class="step-word">${x}</span></li>`).join('');
 $('flow').innerHTML=['描述期望','确认并生成','下载与验证'].map((x,i)=>`<li class="${i===step-1?'active':''}"><b>${i+1}</b>${x}</li>`).join('');
 $('aside-title').textContent=['修改助手','修改说明','交付说明'][step-1];$('object-name').textContent=name;$('object-type').textContent='装备';
 $('aside-copy').innerHTML=step===1?note('从一个具体想法开始','从目录选择一件装备，描述需要修改的字段和目标。')+note('你来决定，AI 帮你理解','AI 整理参数；你确认后，程序才生成文件。')+note('候选与验证','目录候选不代表已游戏验证。支持字段按对象开放。'):step===2?note('这次会发生什么',summary())+note('影响范围','可能影响共用 Stats 的装备及继承记录，不能保证只改背包中的一个实例。')+note('还需要调整？','继续调整参数或补充需求后，需要重新确认。'):note('下一步：本地验证','解压 ZIP → 安装并启用 PAK → 检查效果 → 返回反馈。')+note('请区分制作与验证','文件和打包检查通过，本包游戏效果仍需验证。')+`<section class="note"><h4>验证后告诉我们</h4><div class="feedback-buttons">${button('success-feedback','成功使用')}${button('problem-feedback','遇到问题')}</div><p>制作编号：${esc(plan?.plan_id)}</p></section>`;
 if(step===1&&session?.detail.presentation){const p=session.detail.presentation;$('aside-copy').insertAdjacentHTML('afterbegin',note(p.kind,`${esc(p.effect)}<br>获取：${esc(p.location)}`));}
 if(step===1){
 const pending=[...(session?.questions||[]),...(session?.unsupported||[]).map(x=>'不支持：'+x)];
 const history=(session?.history||[]).slice(-6).map(h=>`<div class="live-turn"><strong>你：</strong>${esc(h.text||'手动参数更新')}<p>${esc(h.error?.message||h.interpretation?.explanation||'已保存参数')}</p></div>`).join('');
 $('panel').innerHTML=`<form id="prompt-form"><div class="picker"><label>修改对象</label><button id="pick" type="button" aria-haspopup="dialog">${esc(name)} · 装备 <span>⌄</span></button></div>${pending.length?`<div class="live-warning" role="status">${pending.map(esc).join('<br>')}</div>`:''}<div class="live-history">${history}</div><label class="prompt-label" for="prompt">${pending.length?'请补充或修改期望':'你想怎么修改？'}</label><textarea id="prompt" maxlength="4000" aria-describedby="error" placeholder="例如：重量减半，保留其他效果。">${esc(input)}</textarea>${errorBox()}<div class="suggestions"><p>试试这些想法</p><button type="button" data-example="基础伤害改为2d6。">↗ 基础伤害2d6</button><button type="button" data-example="重量减半。">↗ 重量减半</button></div><div class="actions">${session?button('manual','直接填写参数'):''}<button class="primary" type="submit">解析修改期望 →</button></div></form>`;
 $('prompt').oninput=()=>{input=$('prompt').value;storage.set('input',input);};
 $('prompt-form').onsubmit=e=>{e.preventDefault();send();};
 $('prompt').onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('prompt-form').requestSubmit();}};
 document.querySelectorAll('[data-example]').forEach(b=>b.onclick=()=>{input=b.dataset.example;storage.set('input',input);render();$('prompt').focus();});
 bind('pick',picker);bind('manual',edit);
 }
 if(step===2){
 $('panel').innerHTML=`<p class="label">${esc(name)}</p><p class="question">${esc(session?.explanation||'请核对本次修改')}</p><hr class="separator"><h2>已理解，先确认这次修改。</h2>${rows().map(r=>`<div class="difference"><span class="field">${esc(labels[r.field])}</span><div class="values ${r.field==='name'?'name':''}"><span class="old">${esc(display(r.field,r.original))}</span><span class="arrow" aria-label="改为">→</span><span class="target">${esc(display(r.field,r.new))}</span></div></div>`).join('')}<p class="body-copy">仅修改列出的字段。本次新包尚未游戏验证。</p>${plan?.experimental?'<label class="live-check"><input id="experimental" type="checkbox">我接受本方案的参数或组合尚待游戏验证。</label>':''}${errorBox()}<div class="actions">${button('edit','继续调整')}${button('confirm','确认并生成 →',true)}</div>`;
 bind('edit',edit);bind('confirm',generate);
 }
 if(step===3){$('panel').innerHTML=`<p class="label">生成结果 / 检查通过</p><h2>${esc(name)}</h2><p class="question">${summary()}</p><hr class="separator"><ol class="files"><li><b>01</b><strong>PAK 修改包</strong><small>解压后安装启用</small></li><li><b>02</b><strong>修改清单</strong><small>确认参数与检查结果</small></li><li><b>03</b><strong>使用说明</strong><small>安装、验证与停用步骤</small></li></ol><p class="body-copy">下载有效期：生成后 7 天。下载不代表安装或游戏验证成功。</p>${errorBox()}<div class="actions">${button('instructions','安装与验证说明')}${button('download','下载 ZIP ↓',true)}</div>`;
 bind('instructions',instructions);bind('download',download);bind('success-feedback',()=>feedback('success'));bind('problem-feedback',()=>feedback('problem'));}
 $('panel').removeAttribute('aria-busy');
}
async function run(label,fn){if(working)return;working=true;try{await fn();}catch(e){render();err(e.message);}finally{working=false;}}
function busy(title,description='正在处理，请稍候。'){ $('panel').setAttribute('aria-busy','true');$('panel').innerHTML=`<div class="busy" role="status"><div class="spinner" aria-hidden="true"></div><h2>${esc(title)}</h2><p>${esc(description)}</p></div>`;}
function remember(){storage.set('session',session?.session_id||null);storage.set('plan',plan?.plan_id||null);}
async function refresh(){if(session){session=await api('/api/ai/sessions/'+session.session_id);plan=session.preview;remember();}}
async function preview(){session=await api('/api/ai/sessions/'+session.session_id+'/preview',body());plan=session.preview;remember();}
function send(){
 input=$('prompt').value;storage.set('input',input);
 if(!input.trim()){err('请先输入修改期望。');$('prompt').setAttribute('aria-invalid','true');$('error').classList.remove('attention-flash');void $('error').offsetWidth;$('error').classList.add('attention-flash');return;}
 if(!session){err('请先选择装备。');picker();return;}
 run('解析',async()=>{
  busy('正在整理修改方案','输入已保留。AI 可能需要约一分钟；完成后可核对或补充。');
  let pending=storage.get('pending');
  if(!pending||pending.session!==session.session_id||pending.body.text!==input){pending={session:session.session_id,body:body({text:input})};storage.set('pending',pending);}
  try{session=await api('/api/ai/sessions/'+session.session_id+'/messages',pending.body);storage.set('pending',null);}
  catch(e){if(!e.network&&e.code!=='session_busy')storage.set('pending',null);try{await refresh();}catch{}throw e;}
  input='';storage.set('input','');plan=null;
  if(session.questions.length||session.unsupported.length||!Object.keys(session.draft).length){remember();render();return;}
  await preview();move(2);
 });
}
function picker(){
 if(working)return;
 modal('选择装备',`<label for="search">搜索装备名称</label><input id="search" type="search" placeholder="输入装备名称"><p class="status-note">仅显示已核实获取方式的装备。普通首饰会单独标注；其他目录候选待核实后开放。</p><div id="object-results" class="object-results" aria-live="polite"></div><div class="actions">${button('previous-page','上一页')}${button('next-page','下一页')}</div><p class="status-note">已核实可获取，不代表本次修改包已通过游戏验证。修改字段按装备开放。</p>`);
 let offset=0,total=0;
 async function search(){const ticket=++pickerSerial;try{const data=await api('/api/equipment?player_available_only=true&limit=20&offset='+offset+'&search='+encodeURIComponent($('search').value));if(ticket!==pickerSerial||!$('object-results'))return;total=data.total;
 $('object-results').innerHTML=data.items.map(item=>{const p=item.presentation;return `<button data-object="${esc(item.object_id)}"><strong>${esc(item.display_name)}</strong><small class="object-kind">${esc(p.kind)} · ${esc(p.effect)}</small><small>获取：${esc(p.location)}</small><small class="object-fields">可修改：${esc(item.capabilities.map(k=>labels[k]).join(' / '))}</small></button>`;}).join('')||'<p>没有找到已核实获取方式的装备。可搜索“白银坠饰”“白银护符”或“第一滴血”。其他目录候选仍待核实。</p>';
 $('previous-page').disabled=offset===0;$('next-page').disabled=offset+20>=total;
 document.querySelectorAll('[data-object]').forEach(b=>b.onclick=async()=>{if(working)return;working=true;try{session=await api('/api/ai/sessions',{object:b.dataset.object});plan=null;input='';storage.set('input','');storage.set('pending',null);storage.set('editor',null);remember();close();step=1;render();$('prompt').focus();}catch(e){$('object-results').textContent=e.message;}finally{working=false;}});
 }catch(e){if($('object-results'))$('object-results').textContent=e.message;}}
 let timer;$('search').oninput=()=>{offset=0;clearTimeout(timer);timer=setTimeout(search,250);};
 bind('previous-page',()=>{offset=Math.max(0,offset-20);search();});bind('next-page',()=>{offset+=20;search();});search();$('search').focus();
}
function edit(){
 if(working||!session)return;
 let draft={...session.draft};const saved=storage.get('editor');if(saved?.session===session.session_id&&saved.version===session.version)draft=saved.changes;
 modal('继续调整','');
 function capture(){document.querySelectorAll('[data-field]').forEach(el=>{draft[el.dataset.field]=el.value;});storage.set('editor',{session:session.session_id,version:session.version,changes:draft});}
 function draw(){const rules=session.detail.field_rules;
 $('dialog-body').innerHTML=`<p>${esc(session.detail.display_name)} · 原值与字段以目录为准</p><form id="edit-form">${Object.entries(draft).map(([field,value])=>{const rule=rules[field];return `<div class="parameter-editor"><label for="edit-${field}">${esc(labels[field])} <small>原值：${esc(display(field,original(field)))}</small></label>${rule.type==='enum'?`<select id="edit-${field}" data-field="${field}">${rule.values.map(v=>`<option value="${v}" ${v===value?'selected':''}>${esc(display(field,v))}</option>`).join('')}</select>`:`<input id="edit-${field}" data-field="${field}" value="${esc(value)}" aria-describedby="edit-error" ${field==='weight_kg'?'inputmode="decimal"':''}>`}<button type="button" data-remove="${field}" class="remove-field">移除此参数</button></div>`;}).join('')}
 ${session.unsupported.length?'<label class="live-check"><input id="supported-only" type="checkbox">仅继续当前填写的支持参数，放弃未支持要求</label>':''}${errorBox('edit-error')}<div class="actions">${button('cancel-edit','取消')}<button class="primary" type="submit">保存修改 →</button></div></form><hr><label for="new-field">增加参数</label><select id="new-field">${Object.keys(rules).filter(k=>!Object.hasOwn(draft,k)).map(k=>`<option value="${k}">${esc(labels[k])}</option>`).join('')}</select>${button('add-field','增加新参数')}<hr><label for="reword">用文字继续调整</label><textarea id="reword" maxlength="4000" placeholder="例如：在当前方案上把重量减半"></textarea>${button('reword-send','解析补充需求')}`;
 document.querySelectorAll('[data-field]').forEach(el=>el.oninput=capture);
 bind('cancel-edit',close);$('cancel-edit').type='button';
 document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{capture();delete draft[b.dataset.remove];storage.set('editor',{session:session.session_id,version:session.version,changes:draft});draw();});
 bind('add-field',()=>{capture();const field=$('new-field').value;if(field){draft[field]=original(field)??'';draw();$('edit-'+field).focus();}});
 async function save(){capture();if(!Object.keys(draft).length)throw Error('请至少填写一个修改参数。');const changes={...draft};if(Object.hasOwn(changes,'weight_kg')){if(String(changes.weight_kg).trim()==='')throw Error('请填写重量。');changes.weight_kg=Number(changes.weight_kg);if(!Number.isFinite(changes.weight_kg))throw Error('重量必须是有限数字。');}
 const request=body({changes,accept_supported_only:$('supported-only')?.checked||false});
 session=await api('/api/ai/sessions/'+session.session_id+'/draft',request);plan=null;storage.set('editor',null);storage.set('pending',null);remember();}
 $('edit-form').onsubmit=async e=>{e.preventDefault();if(working)return;working=true;$('edit-form').setAttribute('aria-busy','true');try{await save();await preview();close();move(2);}catch(e){err(e.message,'edit-error');}finally{working=false;$('edit-form')?.removeAttribute('aria-busy');}};
 bind('reword-send',async()=>{if(working)return;const text=$('reword').value.trim();if(!text){err('请填写补充需求。','edit-error');return;}working=true;try{if(Object.keys(draft).length)await save();input=text;storage.set('input',input);close();step=1;render();}catch(e){err(e.message,'edit-error');}finally{working=false;}if(!$('dialog').open)send();});
 }draw();
}
function generate(){if(working||!plan)return;const experimental=$('experimental')?.checked||false;if(plan.experimental&&!experimental){err('请先接受试验提示。');return;}
 run('生成',async()=>{const result=await api('/api/plans/'+plan.plan_id+'/tasks',{confirmed:true,accept_experimental:experimental});plan=result;remember();await poll();});}
async function poll(){clearTimeout(pollTimer);if(!plan)return;plan=await api('/api/plans/'+plan.plan_id);remember();
 if(plan.status==='succeeded'){move(3);return;}
 if(['queued','generating'].includes(plan.status)){busy(plan.status==='queued'?'正在等待制作':'正在生成并检查修改包','可刷新页面恢复进度，请勿重复制作。');pollTimer=setTimeout(()=>poll().catch(e=>{render();err(e.message+' 请刷新查询制作结果。');}),1200);return;}
 step=2;render();err('本次制作未完成（'+(plan.failure_stage||plan.status)+'）。请重新核对方案后重试。');
 const report=document.createElement('button');report.className='secondary';report.textContent='反馈本次制作问题';report.onclick=()=>feedback('problem');$('panel').append(report);
 // A failed plan cannot be reused; create a fresh immutable preview on the next click.
 bind('confirm',()=>run('重新预览',async()=>{await preview();render();err('已重新预览，请核对并再次确认生成。');}));
}
function instructions(){run('说明',async()=>{const data=await api('/api/plans/'+plan.plan_id+'/instructions');modal('安装与验证说明',`<pre class="live-instructions">${esc(data.text)}</pre>`);});}
function download(){run('下载',async()=>{const response=await fetch('/api/plans/'+plan.plan_id+'/download');if(!response.ok){const data=await response.json();throw Error(data.detail?.message||'下载失败，请重试。');}const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download=plan.plan_id+'.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
function feedback(outcome){const request_id=crypto.randomUUID();modal(outcome==='success'?'成功使用反馈':'问题反馈',`<p>${summary()}</p><form id="feedback-form"><label for="feedback-stage">反馈阶段</label><select id="feedback-stage">${[['game_effect','游戏效果'],['installation','安装启用'],['download','下载'],['generation','生成'],['packaging','打包']].filter(x=>outcome==='problem'||x[0]==='game_effect').map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select><label for="game-version">游戏版本（可选）</label><input id="game-version" maxlength="100"><label for="feedback-detail">${outcome==='problem'?'问题描述（必填）':'效果与说明（可选）'}</label><textarea id="feedback-detail" maxlength="2000"></textarea><p>反馈保存在服务器，仅记录用户报告，不自动标记为实际游戏验证。</p>${errorBox('feedback-error')}<button class="primary" type="submit">提交反馈</button></form>`);
 let sent=false;$('feedback-form').onsubmit=async e=>{e.preventDefault();if(sent)return;sent=true;try{await api('/api/plans/'+plan.plan_id+'/feedback',{request_id,outcome,stage:$('feedback-stage').value,game_version:$('game-version').value,detail:$('feedback-detail').value});$('dialog-body').innerHTML='<p role="status">反馈已保存到服务器。感谢提供本次使用结果。</p>';}catch(e){err(e.message,'feedback-error');}finally{sent=false;}};}
function collapse(value){document.body.classList.toggle('help-collapsed',value);$('toggle-help').setAttribute('aria-expanded',String(!value));$('toggle-help').setAttribute('aria-label',value?'展开右侧说明':'收起右侧说明');$('help-panel').inert=value;$('help-panel').setAttribute('aria-hidden',String(value));$('help-arrow').textContent=value?'‹':'›';storage.set('collapsed',value);}
collapse(Boolean(storage.get('collapsed')));$('toggle-help').onclick=()=>collapse(!document.body.classList.contains('help-collapsed'));
$('reset').onclick=()=>{if(working||['queued','generating'].includes(plan?.status))return;clearTimeout(pollTimer);session=null;plan=null;input='';for(const k of ['input','editor','pending'])storage.set(k,null);remember();move(1);};
window.addEventListener('popstate',e=>{if(working)return;if(['queued','generating'].includes(plan?.status)){poll().catch(e=>err(e.message));return;}step=Math.min(e.state?.step||1,plan?.status==='succeeded'?3:plan?2:1);render();});
render();
run('恢复',async()=>{const sid=storage.get('session'),pid=storage.get('plan');if(!sid)return;session={session_id:sid};try{await refresh();if(pid)plan=await api('/api/plans/'+pid);if(plan?.status==='succeeded'){step=3;render();}else if(['queued','generating','interrupted','failed'].includes(plan?.status)){await poll();}else if(plan){step=2;render();}else{render();}}catch(e){session=null;plan=null;render();throw e;}});
})();
