from pathlib import Path
p=Path('web/craft.js')
s=p.read_text(encoding='utf-8')
start=s.index('function renderEdit()')
end=s.index('function textReviewMarkup()',start)
new=r'''function resultItems(){
 const items=[],add=(category,title,html,operations=[],texts=[],extra='')=>items.push({category,title,html,operations,texts,extra});
 for(const k of ['name','description']){
  const pending=state.texts.find(t=>t.target.owner==='equipment'&&t.target.field===k);
  const value=pending?.mode==='exact'?pending.text:state.plan.display[k];
  if(value!=null||pending)add('名称与说明',labels[k],`<p class="prewrap">${esc(value||'等待生成候选')}</p>${pending?'<small>待核对，确认前将与实际效果检查。</small>':''}`,[],[textReq('equipment',k,null,'reset')]);
 }
 for(const [k,v] of Object.entries(state.plan.parameters))if(v!=null){const original=state.effective_values[k]?.original;add('基础参数',labels[k],`<p>${esc(show(original))} → <strong>${esc(show(v))}</strong></p>`,[op('restore_parameter',k)]);}
 for(const e of state.plan.effects){
  const ids=[...state.plan.effects.filter(x=>x.status_draft_id===e.id).map(x=>x.id),e.id];
  add('效果与技能',e.display?.name||labels[e.kind],effectCard(e,false)+(ids.length>1?'<small>撤销此状态时，会一并撤销引用它的触发效果。</small>':''),ids.map(id=>op('remove_effect',id)),[],`<button data-text-effect="${esc(e.id)}">填写词条（可选）</button>`);
 }
 for(const p of state.original_passives.filter(p=>p.removed))add('原生效果','移除原生效果',`<p>${esc(p.name)}</p>`,[op('restore_original_passive',p.id)]);
 for(const k of ['appearance_equipment','icon','acquisition'])if(state.plan[k])add('资源与获取',labels[k],`<p>${esc(k==='acquisition'?'第一章 · 翠绿林地 · 达蒙':show(state.plan[k]))}</p>`,[op('select_reference',k,{reference_id:null})]);
 if(state.plan.template_behavior==='preserve_reviewed')add('资源与获取','保留特殊模板行为','<p>已接受基础装备经过核对的特殊行为。</p>',[op('set_template_behavior','equipment',{value:'reject_special',audit_id:state.template_audit_id,evidence_quote:'不再接受特殊模板行为'})]);
 return items;
}
function renderEdit(){
 const items=resultItems(),groups=[...new Set(items.map(x=>x.category))];
 $('#workspace').innerHTML=`<section class="card emphasis"><h2>${esc(state.base_name)}</h2><label for="prompt">告诉我，你想怎么改？</label><textarea id="prompt" maxlength="4000" placeholder="例如：名字改为 Fool，重量改为 0。"></textarea><div class="actions"><button class="primary" id="send">解析并更新方案</button><button id="switch-base">切换基础装备／模式</button></div><small>继续输入可以追加或调整修改；无法完成的要求会保留。</small></section>${issueMarkup()}${state.has_parsed?`<section class="card" id="parsed-plan"><h2>当前采用的修改（${items.length}）</h2><p class="muted">点击 × 撤销对应修改，其余修改继续保留。</p>${groups.map(g=>`<section class="result-category"><h3>${esc(g)}</h3>${items.map((x,i)=>x.category===g?`<article class="result-item"><div class="row"><strong>${esc(x.title)}</strong><button class="remove-result" data-remove-result="${i}" aria-label="撤销${esc(x.title)}" title="撤销这项修改">×</button></div>${x.html}${x.extra}</article>`:'').join('')}</section>`).join('')||'<p>当前没有采用任何修改，请继续描述需求。</p>'}${(state.review?.items||[]).some(i=>i.source_status==='conflict'||i.source_status==='uncertain'||i.proposal_status==='conflict')?`<div class="issue"><h3>需要确认的文案</h3>${textReviewMarkup()}</div>`:''}<div class="actions"><button id="preview" class="primary">核对并进入确认</button>${state.snapshots.length?'<button id="undo">撤销上次操作</button>':''}</div></section>`:''}`;
 $('#send').onclick=()=>action('message',{text:$('#prompt').value,answers:$('#prompt').dataset.issue?[$('#prompt').dataset.issue]:[]});
 $('#switch-base').onclick=switchContext;
 if($('#preview'))$('#preview').onclick=preparePreview;
 if($('#undo'))$('#undo').onclick=()=>{const quote='撤销到上个方案';edit([op('restore_snapshot','equipment',{snapshot_id:state.snapshots.at(-1).id,evidence_quote:quote})],[],{quote});};
 document.querySelectorAll('[data-remove-result]').forEach(b=>b.onclick=async()=>{const x=items[Number(b.dataset.removeResult)],input=$('#prompt').value;const result=await edit(x.operations,x.texts,{quote:x.title==='保留特殊模板行为'?'不再接受特殊模板行为':`不再采用${x.title}修改`});if(result){$('#prompt').value=input;notice(`已撤销「${x.title}」，其余修改已保留。`);}});
 document.querySelectorAll('[data-text-effect]').forEach(b=>b.onclick=()=>editText(b.dataset.textEffect));
 bindIssues();bindAdopt();
}
'''
s=s[:start]+new+s[end:]
p.write_text(s,encoding='utf-8')
