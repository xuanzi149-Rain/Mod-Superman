"""Strict interpretation contract and deterministic draft operations."""
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from scripts.generate_equipment import FIELDS, validate_request
from scripts.generate_mod import ValidationError

PROMPT_VERSION = 'equipment-v1'


def parameter_message(error):
    message = str(error)
    return {
        'Weight must be a JSON number in kg.': '重量必须填写数值，单位为千克。',
        'Weight must be 0..100 kg, at most three decimals.': '重量须在 0～100 kg 内且最多三位小数；请调整目标值。',
        'Dice must be NdS, count 1..10, sides 4/6/8/10/12/20.': '伤害需填写 NdS，例如 2d6；骰子数为1～10，面数为4、6、8、10、12或20。',
        'Name must be 1..60 characters without control characters.': '名称须为1～60个字符，不能包含换行或控制字符。',
        'Rarity must be Common/Uncommon/Rare/VeryRare/Legendary.': '请从普通、精良、稀有、珍奇或传奇对应的稀有度选项中选择。',
        'Changes must be a nonempty object.': '请至少填写一项修改。',
        'Unknown equipment ID; select an ID from --list.': '请选择目录中的装备对象。',
    }.get(message, message)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Operation(StrictModel):
    field: Literal['damage', 'versatile_damage', 'name', 'weight_kg', 'rarity']
    operation: Literal['set', 'remove', 'add', 'subtract', 'multiply']
    value: str | int | float | None
    basis: Literal['current', 'original']
    unit: Literal['kg', 'g'] | None

    @model_validator(mode='after')
    def check_operation(self):
        if self.operation == 'remove':
            if self.value is not None or self.unit is not None:
                raise ValueError('撤销操作不能包含数值或单位。')
        elif self.field == 'weight_kg':
            if type(self.value) not in (int, float):
                raise ValueError('重量操作需要数值。')
            if (self.operation == 'multiply' and self.unit is not None or
                    self.operation != 'multiply' and self.unit is None):
                raise ValueError('重量单位无效。')
        elif self.operation != 'set' or not isinstance(self.value, str) or self.unit is not None:
            raise ValueError('该字段只支持字符串赋值或撤销。')
        return self


class Interpretation(StrictModel):
    result: Literal['suggestion', 'clarify', 'unsupported']
    operations: list[Operation] = Field(max_length=5)
    questions: list[str] = Field(max_length=5)
    unsupported: list[str] = Field(max_length=5)
    explanation: str = Field(max_length=1500)

    @model_validator(mode='after')
    def check_result(self):
        fields = [op.field for op in self.operations]
        if len(set(fields)) != len(fields):
            raise ValueError('同字段重复操作，需澄清。')
        if bool(self.questions) != (self.result == 'clarify'):
            raise ValueError('澄清状态与问题不一致。')
        if self.result == 'unsupported' and (not self.unsupported or self.operations):
            raise ValueError('不支持状态不一致。')
        if any(not text.strip() or len(text) > 1000 for text in self.questions + self.unsupported):
            raise ValueError('问题文本无效。')
        return self


def apply_operations(object_id, draft, interpretation, catalog):
    item = catalog['items'][object_id]
    updated = dict(draft)
    trace = []
    for op in interpretation.operations:
        if op.field not in item['capabilities']:
            raise ValidationError('当前装备不支持字段：' + op.field)
        original = item['display_name'] if op.field == 'name' else item['original'].get(FIELDS[op.field])
        base = draft.get(op.field, original) if op.basis == 'current' else original
        if op.operation == 'remove':
            updated.pop(op.field, None)
            trace.append({**op.model_dump(), 'base': base, 'new': original, 'check': '撤销草稿字段'})
            continue
        value = op.value
        if op.field == 'weight_kg':
            try:
                operand = Decimal(str(value))
                if op.unit == 'g':
                    operand /= Decimal(1000)
                if op.operation != 'set':
                    base_decimal = Decimal(str(base))
                    if not base_decimal.is_finite():
                        raise InvalidOperation
                    operand = {'add': lambda: base_decimal + operand,
                               'subtract': lambda: base_decimal - operand,
                               'multiply': lambda: base_decimal * operand}[op.operation]()
                if not operand.is_finite() or not 0 <= operand <= 100 or operand != operand.quantize(Decimal('.001')):
                    raise ValidationError('重量须在 0～100 kg 内且最多三位小数；请给出明确合法目标，不会自动取整。')
                value = float(operand)
            except (InvalidOperation, ValueError, TypeError):
                raise ValidationError('无法读取重量原值，请给出明确目标重量。') from None
        updated[op.field] = value
        trace.append({**op.model_dump(), 'base': base, 'new': value, 'check': '通过'})
    if updated:
        updated, _ = validate_request({'object': object_id, 'changes': updated}, catalog=catalog, allow_unverified=True)
        updated = updated['changes']
    return updated, trace
