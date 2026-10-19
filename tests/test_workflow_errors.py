import unittest
from backend.workflow_errors import explain_failure

class WorkflowErrorTests(unittest.TestCase):
    def test_reported_model_failure_has_cause_and_recovery(self):
        message=explain_failure('message',ValueError('invalid_issue_resolution'))
        self.assertIn('旧问题处理记录',message)
        self.assertIn('本轮原文',message)
        self.assertIn('重新点击',message)
        self.assertIn('无需检查装备参数',message)

    def test_failure_types_are_distinct_and_raw_details_are_private(self):
        examples={'schema:operations:secret data':'格式', 'stale_text':'不一致',
                  'effective_facts_incomplete':'资料不完整','context_budget_exceeded':'容量',
                  'requirement_quote_not_in_message':'原文','unknown-secret-value':'暂时无法确定具体原因'}
        for error,expected in examples.items():
            with self.subTest(error=error):
                message=explain_failure('message',ValueError(error))
                self.assertIn(expected,message)
                self.assertNotIn(error,message)
