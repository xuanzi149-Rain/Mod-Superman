(()=>{'use strict';
const M=PrototypeModel,$=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let s=M.create(),job=0,returnFocus=null;
const scenario=new URLSearchParams(location.search).get('scenario');let failureUsed=false;
const titles=[['生成你的','私人定制Mod！'],['确认参数'],['修改已就绪','带进你的游戏。']];
const stepNames=['描述期望','确认并生成','下载与验证'];
const examples={damage:'把基础伤害骰数量翻倍，保留其他效果。',name:'把中文名称改为曙光短剑，保留其他效果。',heal:'把治愈真言的施法距离改为36米。'};
function note(title,body){return `<section class="note"><h4>${title}</h4><p>${body}</p></section>`;}
function action(id,label,primary=false){return `<button id="${id}" class="${primary?'primary':'secondary'}">${label}</button>`;}
function difference(){return M.rows(s.plan).map(p=> `<div class="difference"><span class="field">${esc(p.label)}</span><div class="values ${p.kind==='name'?'name':''}"><span class="old">${esc(p.old)}</span><span class="arrow" aria-label="改为">→</span><span class="target">${display(p)}</span></div></div>`).join('');}
function display(p){return esc(p.kind==='rarity'?(M.rarities[p.value]||p.value):p.value);}
function summary(plan=s.plan){return M.rows(plan).map(p=>esc(p.label)+'：'+esc(p.old)+' → '+display(p)).join('<br>');}
function saveHistory(replace=false){try{history[replace?'replaceState':'pushState']({prototype:JSON.parse(JSON.stringify({...s,busy:false}))},'',`#step-${s.step}`);}catch{}}
function move(step){s.step=step;saveHistory();render();$('heading').focus();}
function error(msg,id='error'){const el=$(id);el.textContent=msg;el.focus();}
function errorBox(){return '<div id="error" class="error" role="alert" tabindex="-1"></div>';}
function bind(id,fn){if($(id))$(id).onclick=fn;}
function render(){
 const n=s.step,object=M.objects[s.object];
 $('heading').innerHTML=titles[n-1].map(x=>`<span>${x}</span>`).join('');
 $('steps').innerHTML=['描述','确认','下载'].map((t,i)=>`<li class="${i===n-1?'active':''}" ${i===n-1?'aria-current="step"':''}><b>0${i+1}</b><span class="step-word">${t}</span></li>`).join('');
 $('flow').innerHTML=stepNames.map((t,i)=>`<li class="${i===n-1?'active':''}"><b>${i+1}</b>${t}</li>`).join('');
 $('aside-title').textContent=['修改助手','修改说明','交付说明'][n-1];$('object-type').textContent=object.type;$('object-name').textContent=object.name;
 const impact=s.object==='sword'?'可能影响共用该记录的装备，<br>不承诺只修改一个实例。':'修改所选技能记录的距离，<br>本次新包效果仍需游戏验证。';
 if(n===1)$('aside-copy').innerHTML=note('从一个具体想法开始','选择一件装备或一个技能，<br>告诉我们你希望怎样改变它。')+note('你来决定，AI 帮你理解','AI 会整理修改参数。<br>你确认后，才生成修改文件。')+note('保留清晰的修改边界','只修改已支持的字段；<br>有歧义时，先补充说明。');
 if(n===2)$('aside-copy').innerHTML=note('这次会发生什么',summary())+note('影响范围',impact)+note('还需要调整？','点击「继续调整」补充期望。<br>参数变化后，需要重新确认。');
 if(n===3)$('aside-copy').innerHTML=note('下一步：本地验证','1. 按说明打包并安装<br>2. 进入游戏检查修改效果<br>3. 返回这里反馈结果')+note('请区分制作与验证','文件生成成功，并不代表<br>安装或游戏验证已通过。')+`<section class="note"><h4>验证后告诉我们</h4><div class="feedback-buttons">${action('success-feedback','成功使用')}${action('problem-feedback','遇到问题')}</div><p class="status-note">${s.feedback?'已记录本地演示反馈：'+esc(s.feedback.status):'当前为交互预览，不提供真实 Mod 下载或反馈提交。'}</p></section>`;
 if(n===1)$('panel').innerHTML=`<form id="prompt-form"><div class="picker"><label>修改对象</label><button id="pick" type="button" aria-haspopup="dialog">${object.name} · ${object.type}<span aria-hidden="true">⌄</span></button></div><label class="prompt-label" for="prompt">你想怎么修改？</label><textarea id="prompt" maxlength="1200" aria-describedby="error" placeholder="${s.object==='sword'?'例如：把基础伤害骰数量翻倍，保留其他效果。':'例如：施法距离改为36米。'}">${esc(s.draft)}</textarea>${errorBox()}<div class="suggestions"><p>试试这些想法</p><button type="button" data-example="damage">↗ 基础伤害翻倍</button><button type="button" data-example="name">↗ 修改装备名称</button><button type="button" data-example="heal">↗ 施法距离改为36米</button></div><div class="actions end"><button class="primary" type="submit">解析修改期望 →</button></div></form>`;
 if(n===2)$('panel').innerHTML=`<p class="label">你的期望</p><p class="question">${esc(s.plan.question)}</p><hr class="separator"><h2>已理解，先确认这次修改。</h2>${difference()}<p class="body-copy">仅修改上述列出的字段，其他配置不主动改写。</p>${errorBox()}<div class="actions">${action('edit','继续调整')}${action('confirm','确认并生成 →',true)}</div>`;
 if(n===3)$('panel').innerHTML=`<p class="label">生成结果 / 示例</p><h2>${object.name}</h2><p class="question">${summary()}</p><hr class="separator"><ol class="files"><li><b>01</b><strong>修改文件</strong><small>用于本地打包</small></li><li><b>02</b><strong>修改清单</strong><small>核对字段与参数</small></li><li><b>03</b><strong>使用说明</strong><small>打包、安装与验证步骤</small></li></ol>${errorBox()}<div class="actions">${action('instructions','安装与验证说明')}${action('download','下载修改文件 ↓',true)}</div>`;
 bind('pick',picker);bind('confirm',()=>{try{M.confirm(s);generate();}catch(e){error(e.message);}});bind('edit',edit);bind('generate',generate);bind('download',download);bind('instructions',instructions);bind('success-feedback',()=>feedback('成功使用'));bind('problem-feedback',()=>feedback('遇到问题'));
 if($('prompt-form')){
  $('prompt-form').onsubmit=e=>{e.preventDefault();parsePrompt();};$('prompt').oninput=()=>{s.draft=$('prompt').value;};
  $('prompt').onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('prompt-form').requestSubmit();}};
  document.querySelectorAll('[data-example]').forEach(b=>b.onclick=()=>{s.object=b.dataset.example==='heal'?'heal':'sword';s.draft=examples[b.dataset.example];s.plan=null;s.confirmed=null;s.result=null;render();$('prompt').focus();});
 }
}
function busy(label,description){s.busy=true;$('panel').setAttribute('aria-busy','true');$('panel').innerHTML=`<div class="busy" role="status"><div class="spinner" aria-hidden="true"></div><h2>${label}</h2><p>${description}</p></div>`;}
async function parsePrompt(){
 if(s.busy)return;const q=$('prompt').value.trim();s.draft=q;
 if(!q){$('prompt').setAttribute('aria-invalid','true');error('请先输入修改期望。');const hint=$('error');hint.classList.remove('attention-flash');void hint.offsetWidth;hint.classList.add('attention-flash');return;}
 const token=++job;busy('正在整理修改方案','保留当前对象，检查你的修改期望。');await new Promise(r=>setTimeout(r,650));if(token!==job)return;
 s.busy=false;$('panel').removeAttribute('aria-busy');
 if(scenario==='parse-error'&&!failureUsed){failureUsed=true;render();error('解析暂时失败，请再次点击“解析修改期望”重试。输入内容已保留。');return;}
 const result=M.parse(s.object,q);if(result.error){render();error(result.error);return;}
 M.setPlan(s,result.plan);move(2);
}
async function generate(){
 if(s.busy)return;const token=++job;busy('正在生成修改文件','正在演示校验与制作过程，请稍候。');await new Promise(r=>setTimeout(r,850));if(token!==job)return;
 s.busy=false;$('panel').removeAttribute('aria-busy');
 if(scenario==='generate-error'&&!failureUsed){failureUsed=true;render();error('文件生成失败。已保留确认参数，请点击“确认并生成”重试。');return;}
 try{M.generate(s);move(3);}catch{move(2);error('参数已变化，请重新确认后再生成。');}
}
function modal(title,html){returnFocus=document.activeElement;$('dialog-title').textContent=title;$('dialog-body').innerHTML=html;$('dialog').showModal();}
function close(){ $('dialog').close(); }
$('close-dialog').onclick=close;$('dialog').addEventListener('close',()=>{if(returnFocus?.isConnected)returnFocus.focus();else $('heading').focus();});
function picker(){
 modal('选择修改对象',`<div class="tabs"><button data-tab="sword" aria-pressed="true">装备</button><button data-tab="heal" aria-pressed="false">技能示例</button></div><label for="search">搜索名称</label><input id="search" type="search" placeholder="输入装备或技能名称"><div id="object-results" class="object-results" aria-live="polite"></div><p class="status-note">此原型保留先前的两个演示对象，不代表正式网站的完整支持目录。</p>`);
 let tab=s.object;function results(){document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===tab)));const obj=M.objects[tab],q=$('search').value.trim();$('object-results').innerHTML=obj.name.includes(q)?`<button id="choose-object"><strong>${obj.name}</strong><small>${obj.type} · ${tab==='sword'?'基础伤害 / 中文名称':'施法距离示例'}</small></button>`:'<p>没有找到该对象。请更换关键词。</p>';bind('choose-object',()=>{s.object=tab;s.draft='';s.plan=null;s.confirmed=null;s.result=null;close();render();$('prompt').focus();});}
 document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;results();});$('search').oninput=results;results();$('search').focus();
}
function edit(){
 let draft=M.rows(s.plan).map(p=>({...p}));
 modal('继续调整','');
 function capture(){document.querySelectorAll('[data-edit-field]').forEach(input=>{const row=draft.find(c=>c.field===input.dataset.editField);if(row)row.value=input.value;});}
 function editor(c){const id='value-'+c.field;return '<label for="'+id+'">'+esc(c.label)+' <small>原值：'+esc(c.old)+'</small></label>'+(c.kind==='rarity'?'<select id="'+id+'" data-edit-field="'+c.field+'">'+Object.entries(M.rarities).map(([v,label])=>'<option value="'+v+'" '+(v===c.value?'selected':'')+'>'+label+'</option>').join('')+'</select>':'<input id="'+id+'" data-edit-field="'+c.field+'" maxlength="60" value="'+esc(c.value)+'" aria-describedby="edit-error">');}
 function draw(){
 $('dialog-title').textContent='继续调整';
 $('dialog-body').innerHTML='<p>'+esc(M.objects[s.object].name)+' · 保存后统一核对并生成</p><form id="edit-form">'+draft.map(c=>'<div class="parameter-editor">'+editor(c)+'<button type="button" class="remove-field" data-remove="'+c.field+'" '+(draft.length===1?'disabled':'')+'>移除此参数</button></div>').join('')+'<div id="edit-error" class="error" role="alert" tabindex="-1"></div><div class="actions">'+action('cancel-edit','取消')+'<button class="primary" type="submit">保存修改 →</button></div></form><hr><div class="edit-options">'+action('describe-again','用文字重新描述')+action('add-parameter','增加新参数')+'</div><div id="add-fields"></div>';
 $('cancel-edit').type='button';$('cancel-edit').onclick=close;
 $('edit-form').onsubmit=e=>{e.preventDefault();capture();try{const plan=M.changePlan(s.plan,draft);plan.question='修改方案：'+M.rows(plan).map(c=>c.label+'改为'+c.value).join('，')+'。';M.setPlan(s,plan);close();move(2);}catch(e){error(e.message,'edit-error');}};
 document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{capture();draft=draft.filter(c=>c.field!==b.dataset.remove);draw();});
 $('describe-again').onclick=()=>{capture();$('dialog-body').innerHTML='<form id="reword-form"><label for="reword">描述需要调整的参数</label><textarea id="reword" maxlength="1200" placeholder="例如：基础伤害改为3d6"></textarea><p>解析到的字段会更新，其余已添加参数保留。</p><div id="edit-error" class="error" role="alert" tabindex="-1"></div><div class="actions">'+action('back-edit','返回参数编辑')+'<button class="primary" type="submit">更新方案</button></div></form>';$('back-edit').type='button';$('back-edit').onclick=draw;$('reword-form').onsubmit=e=>{e.preventDefault();const result=M.parse(s.object,$('reword').value);if(result.error){error(result.error,'edit-error');return;}const row=M.rows(result.plan)[0],i=draft.findIndex(c=>c.field===row.field);if(i>=0)draft[i]=row;else draft.push(row);draw();};$('reword').focus();};
 $('add-parameter').onclick=()=>{capture();const available=Object.entries(M.fields[s.object]).filter(([key])=>!draft.some(c=>c.field===key));$('add-fields').innerHTML=available.length?'<label for="new-field">选择要增加的参数</label><select id="new-field">'+available.map(([key,f])=>'<option value="'+key+'">'+esc(f.label)+'</option>').join('')+'</select>'+action('append-field','添加到当前方案'):'<p role="status">该对象可修改的参数已全部添加。</p>';bind('append-field',()=>{const key=$('new-field').value,rule=M.fields[s.object][key];if(!rule||draft.some(c=>c.field===key))return;draft.push({field:key,...rule,value:rule.old});draw();$('value-'+key).focus();});if($('new-field'))$('new-field').focus();};
 }
 draw();
}
function instructions(){modal('安装与验证说明',`<p><strong>${esc(M.objects[s.object].name)} · ${summary()}</strong></p><ol><li>正式生成后，先核对修改清单与本次确认的参数。</li><li>按随包说明完成本地打包、加载或安装。</li><li>进入游戏检查目标对象、显示和修改效果。</li><li>返回当前制作结果，反馈成功或遇到的问题。</li></ol><p>本原型仅演示流程，没有生成 PAK 或可安装 Mod。文件生成、打包、安装和游戏验证是不同状态。</p>`);}
function download(){
 if(scenario==='download-error'&&!failureUsed){failureUsed=true;error('下载失败，请再次点击下载重试。当前制作结果已保留。');return;}
 modal('下载内容预览',`<p><strong>${esc(M.objects[s.object].name)}</strong><br>${summary()}</p><p>正式文件包将包含修改文件、修改清单与使用说明。本原型没有生成真实 Mod。</p><p>你可以保存本次方案的演示清单，用于核对交互流程。</p>${action('save-demo','下载演示清单 .txt',true)}`);
 bind('save-demo',()=>{const p=s.result;const content=`Mod-Superman 交互原型演示清单\n不是 Mod，不可安装。\n对象：${M.objects[p.object].name}\n${M.rows(p).map(c=>c.label+'：'+c.old+' → '+c.value).join('\n')}\n参数：已在原型确认\n文件生成：未实际执行\n打包、安装、游戏验证：未执行\n`;
 const url=URL.createObjectURL(new Blob([content],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='Mod-Superman-演示清单.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);});
}
function feedback(status){
 modal('使用反馈 · '+status,`<p>${esc(M.objects[s.object].name)} · ${summary()}</p><form id="feedback-form"><label for="feedback-detail">${status==='遇到问题'?'遇到了什么问题？（必填）':'效果与补充说明（可选）'}</label><textarea id="feedback-detail" maxlength="1000" ${status==='遇到问题'?'required':''} placeholder="例如：安装步骤、游戏内看到的效果"></textarea><p>反馈仅保存在本浏览器的原型记录中，不会提交到服务器。</p><div id="feedback-error" class="error" role="alert" tabindex="-1"></div><button class="primary" type="submit">保存本地演示反馈</button></form>`);
 $('feedback-form').onsubmit=e=>{e.preventDefault();const detail=$('feedback-detail').value.trim();if(status==='遇到问题'&&!detail){error('请描述遇到的问题。','feedback-error');return;}const record={status,detail,plan:{...s.result},time:new Date().toISOString()};let persisted=true;try{const raw=JSON.parse(localStorage.getItem('mod-superman-prototype-feedback')||'[]');const arr=Array.isArray(raw)?raw:[];localStorage.setItem('mod-superman-prototype-feedback',JSON.stringify([...arr,record]));}catch{persisted=false;}s.feedback=record;saveHistory(true);$('dialog-title').textContent='演示反馈已记录';$('dialog-body').innerHTML=`<p>${persisted?'已保存到本浏览器。':'浏览器存储不可用，仅保留在本次页面会话中。'}反馈未上传服务器。</p><p>${esc(M.objects[s.object].name)} · ${summary(s.result)} · ${status}</p>`;render();};
}
function reset(){job++;s=M.create();$('panel').removeAttribute('aria-busy');if($('dialog').open)close();move(1);}
$('reset').onclick=reset;
window.addEventListener('popstate',e=>{if(!e.state?.prototype)return;job++;s=e.state.prototype;s.busy=false;if($('dialog').open)close();$('panel').removeAttribute('aria-busy');render();});
function setHelpCollapsed(collapsed){
 document.body.classList.toggle('help-collapsed',collapsed);
 $('toggle-help').setAttribute('aria-expanded',String(!collapsed));
 $('toggle-help').setAttribute('aria-label',collapsed?'展开右侧说明':'收起右侧说明');
 $('toggle-help').title=collapsed?'展开右侧说明':'收起右侧说明';
 $('help-arrow').textContent=collapsed?'‹':'›';
 $('help-panel').inert=collapsed;
 $('help-panel').setAttribute('aria-hidden',String(collapsed));
 try{localStorage.setItem('mod-superman-help-collapsed',String(collapsed));}catch{}
}
let helpCollapsed=false;try{helpCollapsed=localStorage.getItem('mod-superman-help-collapsed')==='true';}catch{}
setHelpCollapsed(helpCollapsed);
$('toggle-help').onclick=()=>setHelpCollapsed(!document.body.classList.contains('help-collapsed'));
saveHistory(true);render();
})();
