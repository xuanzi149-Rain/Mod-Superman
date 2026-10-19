"""Process-local authority for adopted text; never accept a model-supplied receipt."""
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass

_KEY = secrets.token_bytes(32)
VERSION = 'task8-text-v2'
COMPILER_VERSION = 'v11-task8-v5'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class TextReceipt:
    binding: str
    signature: str
    path: str


def _binding(plan, resources):
    return fingerprint({'version': VERSION, 'compiler_version': COMPILER_VERSION, 'plan': plan.model_dump(mode='json'),
                        'resources': fingerprint(resources)})


def issue_receipt(plan, resources, *, path):
    """Trusted workflow only, after adopted text passed review or standard recovery."""
    if path not in ('ai_reviewed', 'standard_used') or plan.unresolved:
        raise ValueError('Unresolved plan cannot receive text approval')
    binding = _binding(plan, resources)
    return TextReceipt(binding, hmac.new(_KEY, (binding + path).encode(), hashlib.sha256).hexdigest(), path)


def valid_receipt(receipt, plan, resources):
    if not isinstance(receipt, TextReceipt):
        return False
    expected = hmac.new(_KEY, (receipt.binding + receipt.path).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, receipt.signature) and receipt.binding == _binding(plan, resources)
