"""Explain workflow failures without exposing raw model output or resource IDs."""

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
        return '解析或核对结果未通过一致性校验，程序未采用本次结果。请保留输入重试；若再次出现，请反馈当前需求和此提示，不必自行猜测或补填技术信息。'
    return '这项操作未能通过当前方案校验，原因已记录。请刷新恢复最新草稿后重试；若仍失败，请反馈刚才的操作，暂勿反复修改无关参数。'
