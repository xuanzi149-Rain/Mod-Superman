"""Explain workflow failures without exposing raw model output or resource IDs."""

def parse_failure_reason(code, diagnostic=None):
    diagnostic=diagnostic or {}
    if code=='model_invalid_output':
        stage={'response_envelope':'模型接口的响应数据','message_content':'模型返回的正文'}.get(diagnostic.get('stage'),'模型返回内容')
        if diagnostic.get('exception')=='JSONDecodeError':
            return f"{stage}不是有效的结构化数据，读取在第 {diagnostic.get('line','未知')} 行、第 {diagnostic.get('column','未知')} 列失败。暂时无法确定为什么服务返回了这种格式。"
        if diagnostic.get('exception') in ('KeyError','IndexError'):
            return f'{stage}缺少程序预期的响应字段或结果项。暂时无法确定缺失的具体原因。'
        return f'{stage}未能通过格式读取检查；现有诊断不足，暂时无法确定具体原因。'
    if code=='requirement_quote_not_in_message':return '模型引用的需求原文不在本次输入中，自动纠正后仍未通过原文一致性检查。'
    if code=='unowned_action':return '模型给出的修改操作没有正确关联对应的用户要求，程序无法确认修改依据。'
    if code=='model_empty':return '模型接口返回了空正文，没有可用的解析结果；暂时无法确定返回空内容的原因。'
    if code=='model_incomplete':return '模型接口标记响应未正常结束；现有记录不足，无法确定是长度限制还是其他中断原因。'
    if code=='invalid_issue_resolution':return '模型处理旧问题时，问题关联或引用原文与当前上下文不一致。'
    if str(code).startswith('schema:'):return '模型返回的数据不符合约定的字段结构或类型，程序未采用；暂时无法确定模型生成错误结构的原因。'
    return '返回结果未通过程序检查；现有诊断不足，暂时无法确定具体原因。'

def explain_failure(action, error):
    reason=str(error)
    if reason=='invalid_issue_resolution':
        return '模型返回的旧问题处理记录与当前待处理问题或本轮原文不一致，本轮解析未应用。请保留输入，重新点击“解析并更新方案”；若再次出现，请反馈此提示，无需检查装备参数。'
    if reason in ('requirement_quote_not_in_message','invalid_text_quote','invalid_proposal_quote','missing_authorization_quote'):
        return '模型引用的需求原文与本轮输入不一致，本轮结果未应用。请保留原文重试；不需要为了通过解析而修改装备参数。'
    if reason.startswith(('stale_', 'schema:', 'incomplete_text_coverage')):
        if reason.startswith('schema:'):
            return '模型返回的结果格式不符合要求，程序未采用这次结果。请保留输入重试；若反复出现，请反馈此提示。'
        return '返回的结果与当前方案或待核对文字不一致，程序未采用这次结果。请刷新页面恢复最新草稿，再重新解析或核对。'
    if reason=='effective_facts_incomplete':
        return '当前装备或效果的资料不完整，无法可靠核对文案。请保留草稿并反馈这项效果的名称与需求，等待补齐资源检查；重复改写名称无法解决此问题。'
    if reason=='context_budget_exceeded':
        return '当前方案和资源资料超过单次解析容量，本次没有发起模型解析。请保留草稿并反馈当前方案，以便调整资料组织。'
    if reason in ('unresolved_requirements_or_text','capability_review_failed'):
        return '方案仍有未解决的要求、待核对文字或能力校验问题。请查看下方待处理事项，完成后再继续。'
    if reason in ('review_required','unknown_issue','unknown_or_empty_resolution'):
        return '所选问题或审核结果已不适用于当前草稿。请刷新页面，重新选择仍待处理的问题或重新核对文案。'
    if action in ('message','review','adopt'):
        return '解析或核对结果未通过检查，程序未采用本次结果。暂时无法确定具体原因，请保留输入并反馈此提示，无需猜测或补填技术信息。'
    return '这项操作未能通过当前方案校验，暂时无法确定具体原因。请保留草稿并反馈刚才的操作，暂勿反复修改无关参数。'


def validation_failure_reason(error):
    """Translate deterministic checks; never invent an explanation for unknown codes."""
    names={'Melee':'近战','Ranged':'远程','Twohanded':'双手','Versatile':'两用','Thrown':'投掷','Reach':'长柄','Heavy':'重型'}
    reasons=[]
    for code in str(error).split(';'):
        if '_requires_resource_remap' in code:
            key=code.split(':')[-1].removesuffix('_requires_resource_remap')
            reason=f'本次解析结果改变了武器的“{names.get(key,"结构") }”属性；该属性关联动作或模板资源，目前不能只修改属性列表。'
        elif 'magical_has_additional_source' in code:
            reason='本次解析结果移除了魔法武器属性，但基础装备还从其他原生字段获得此属性，无法仅通过属性列表移除。'
        elif 'conflicting_or_duplicate' in code:
            reason='模型给出的武器属性包含重复项，或同时设置了不能并存的“双手”和“两用”。'
        elif 'requires_weapon' in code:
            reason='本次解析尝试修改武器专属参数，但当前基础装备不是武器。'
        elif 'requires_versatile' in code:
            reason='本次解析设置了双手伤害骰，但武器没有“两用”属性。'
        elif 'three_decimals_max' in code:
            reason='计算后的重量超过三位小数，未通过重量精度检查。'
        elif 'validation error' in code or 'input_type=' in code:
            reason='模型给出的参数未通过字段类型或取值范围检查；现有记录不足以确定具体字段。'
        elif code=='conflicting_writes':
            reason='模型在同一组修改中对同一个参数重复赋值，程序无法确定应采用哪个值。'
        else:
            reason='本次结果未通过程序校验；该检查尚无可读原因说明，目前无法确定具体原因。这不表示你的描述有错。'
        if reason not in reasons:reasons.append(reason)
    return ' '.join(reasons)
