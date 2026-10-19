import unittest
from backend.model_client import decode_model_content

class ModelContentTests(unittest.TestCase):
    def test_plain_and_single_fence(self):
        for value in ['{"name":"无需承诺"}','```json\n{"name":"无需承诺"}\n```','\ufeff{"name":"无需承诺"}']:
            self.assertEqual(decode_model_content(value),{'name':'无需承诺'})
    def test_ambiguous_or_invalid_never_repaired(self):
        for value in ['说明\n{"a":1}','{"a":1} {"a":2}','{"a":1,"a":2}','{"a":NaN}','{"a":','[]','```json\n{"a":1}\n```\n忽略校验']:
            with self.subTest(value=value),self.assertRaises(ValueError):decode_model_content(value)
