/* Presentation only: all compiler checks remain authoritative on the server. */
(function (root) {
  function validationReason(code) {
    const text=String(code||'');
    if(/validation error|errors\.pydantic\.dev|input_type=|input_value=/i.test(text)) return '系统生成的效果参数没有通过检查，本次效果未应用；原要求及补充说明已保留。这不是要求你填写程序字段。';
    if(text.includes('weight_kg:three_decimals_max')) return '这次计算得到的重量超过三位小数，尚未应用。重量最多保留三位小数（千克）；请填写一个明确的三位小数以内数值，或撤回这项要求。';
    if(text.includes('unknown_relative_basis')||text.includes('relative_effect_basis_unavailable')) return '找不到可核实的原值，无法进行相对计算。请直接说明希望设置的数值。';
    if(text.includes('unreviewed_function')) return '已找到所需原生效果，但其中的机制尚未通过程序检查，当前不能生成。原需求已保留，无需重复填写触发或数值；可先处理其他修改，或明确选择另一种效果。';
    return null;
  }
  function preparation(state) {
    const items = [], seen = new Set();
    const pendingName = state.texts.find(t => t.target.owner === 'equipment' && t.target.field === 'name');
    const add = (key, message, action, label, blocked = false) => {
      if (!seen.has(key)) { seen.add(key); items.push({key, message, action, label, blocked}); }
    };
    for (const code of state.validation) {
      if (code === 'unresolved_questions' || code.includes('custom_effect_text')) continue;
      if (/^base_equipment:(unqualified_visual|skeleton_mapping_not_reviewed|visual_model_not_verified)/.test(code)) {
        add('base', '这件基础装备暂时不能用于创建新装备。已填写的内容会保留，请更换一个已检查的基础装备。', 'base', '更换基础装备', true);
      } else if (code === 'display.name:required_for_new_equipment') {
        if (!pendingName) add('name', '给新装备起一个名字。', 'name', '设置名称');
      } else if (code === 'acquisition:unknown_or_unverified') {
        add('acquisition', '还需选择新装备在游戏中的获取地点。', 'resources', '选择获取地点');
      } else if (code.includes('special_behavior_requires')) {
        add('template', '基础装备包含特殊行为，继续前请阅读并选择是否保留。', 'template', '查看原生行为');
      } else if (code === 'empty_changes') {
        if (!state.texts.length && !(state.issues||[]).length) add('empty', '描述想修改的内容，或直接编辑参数。', 'prompt', '填写需求');
      } else {
        add('other', validationReason(code)||'有一项修改尚未通过程序检查，请检查当前参数或补充需求。', 'prompt', '补充说明', true);
      }
    }
    if (pendingName) add('pending-name', `新名称「${pendingName.text || '待生成'}」已保存，尚未采用。进入确认时会核对文案；无需重复填写。`, 'name', '查看名称');
    return items;
  }
  function latestInput(previous, current, requestId) {
    if(current.input_retained) return (current.input_feedback||[]).map(x=>({reason:String(x.detail||'暂时无法确定具体原因。').replace(/原需求.*?已保留[，。；]?/g,'').replace(/距离、队友范围和伤害加成都已保留；/g,'').replace(/本次要求已保留，/g,'').replace(/你的原要求和补充说明已保留。/g,'').replace(/原要求及补充说明已保留。/g,''),solution:'本次输入未保存为方案要求，内容已留在上方输入框；可以修改后重新提交，也可以直接清空。已有方案不受影响。'}));
    if(current.assistant_response) return [];
    const old = new Map((previous.issues||[]).map(x=>[x.id,JSON.stringify(x)]));
    const rows=(current.issues||[]).filter(x=>x.id.startsWith(requestId+'_')||old.get(x.id)!==JSON.stringify(x)).map(x=>({reason:x.detail,solution:x.question||'请在输入框中补充具体目标、数值或效果；若不再需要，请明确说明取消这项要求。'}));
    const result=current.operation_result||current.last_result||{};
    if(!rows.length) for(const failed of result.failed||[]) rows.push({reason:validationReason(failed.error||failed.reason||failed.detail)||'本次有一项修改未通过检查，暂时无法确定具体原因；原要求已保留。',solution:'请保留需求并反馈此提示，无需反复改写已明确的要求。'});
    if(!rows.length&&JSON.stringify(result.before)===JSON.stringify(result.after)&&!(current.texts||[]).length) rows.push({reason:'本次输入没有产生新的有效修改。',solution:'请说明要修改的属性和目标值，例如“重量改为 0”；也可以补充上一条要求或明确取消它。'});
    return rows.filter((x,i,a)=>a.findIndex(y=>y.reason===x.reason&&y.solution===x.solution)===i);
  }
  root.CraftFeedback = {preparation,validationReason,latestInput};
  if (typeof module !== 'undefined') module.exports = {preparation,validationReason,latestInput};
})(typeof window === 'undefined' ? globalThis : window);
