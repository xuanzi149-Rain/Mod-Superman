import unittest
from backend.workflow_errors import validation_failure_reason
class FailureReasonTests(unittest.TestCase):
 def test_structural_fields(self):
  reason=validation_failure_reason('parameters.weapon_properties:Thrown_requires_resource_remap;parameters.weapon_properties:Melee_requires_resource_remap')
  self.assertIn('投掷',reason);self.assertIn('近战',reason)
 def test_unknown(self):
  self.assertIn('无法确定具体原因',validation_failure_reason('new_unknown_check'))
 def test_magic(self):
  self.assertIn('其他原生字段',validation_failure_reason('parameters.weapon_properties:magical_has_additional_source'))
