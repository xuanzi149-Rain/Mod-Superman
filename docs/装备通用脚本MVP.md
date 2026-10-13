# 装备通用脚本 MVP 第一版

日期：2026-10-13。依据用户最新要求，将装备支持范围从指定样例扩大为本地数据可识别的装备候选；法术继续使用原来的治愈真言接口。

## 已实现的流程

从本地游戏数据建立装备目录 → 按目录选择对象 ID → 填写规定字段的 JSON → 确认参数 → Python 校验并生成最小修改文件 → LSLib 打包 → 解包逐文件比较 → 输出包、清单与说明。

生成阶段不调用 AI，不需要为每件装备编写脚本，也不依赖 Toolkit 界面操作。Python 只使用标准库；PAK 打包仍调用 LSLib 的 Divine.exe。

## 当前目录范围

收录 1,872 个 RootTemplate 候选，对应 1,113 条独立装备 Stats 记录。类别包含武器、盾牌、躯干防具、头部、手套、靴子、披风、戒指、项链及服装。多个模板可能共用 Stats；这些数字不等于已验证可在正常游戏获得的装备数量。

目录来自已提取的 Shared、SharedDev、Gustav、GustavDev、GustavX 的 Weapon/Armor、RootTemplates 和简体中文文本，并单独解析 Honour Stats 继承。目录记录输入文件 SHA256、字段来源、普通及荣誉规则的原值。该快照不是对所有补丁及第三方 Mod 数据的完整合并；不宣称覆盖所有当前游戏对象。

| 用户参数 | 数据字段 | 输入规则（本产品限制） | 可用模板数 |
|---|---|---|---:|
| `damage` | Weapon.Damage | `NdS`；骰数 1–10，面数 4/6/8/10/12/20 | 689 |
| `versatile_damage` | Weapon.VersatileDamage | 同上；仅原数据存在双手伤害骰的武器 | 182 |
| `name` | 原 DisplayName handle 的中文文本 | 1–60 字符，禁止控制字符 | 1,683 |
| `weight_kg` | Weapon/Armor.Weight | 0–100 kg，最多三位小数 | 1,872 |
| `rarity` | Weapon/Armor.Rarity | Common / Uncommon / Rare / VeryRare / Legendary | 1,872 |

数值限制是首版产品规则，不代表游戏引擎支持的上下限。稀有度未显式赋值时目录保留 null，不编造原值。稀有度不会赋予对应的附魔或被动；重量、稀有度修改也不承诺售价保持不变。

189 个模板的名称句柄被不同或无法识别的 Stats 记录共用，第一版禁止改名，避免连带改名。伤害与双手伤害分别提交，修改前者不会自动同步后者。护甲不开放武器伤害。

## 运行方式

在项目目录打开 PowerShell。当前可用运行时是 Python 3.12.14；脚本使用 Python 3.11 可用的标准库语法。机器上的 `py -3.11` 先前无法启动，本次使用下面的已验证路径。

```powershell
$python = 'C:\Users\17583\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

# 查询目录；返回稳定对象 ID、原值、允许字段及影响范围。
& $python scripts/generate_equipment.py --list --search '第一滴血' --limit 10
& $python scripts/generate_equipment.py --list --category weapon --search '长剑' --limit 10
& $python scripts/generate_equipment.py --rules

# 已知样例的参数确认后，直接生成 PAK。
& $python scripts/generate_equipment.py --request requests/equipment-mvp/first-blood.json --confirmed

# 新对象、新数值、组合修改的测试包，需显式启用实验模式。
& $python scripts/generate_equipment.py --request requests/equipment-mvp/ring.json --confirmed --experimental
```

输入示例：

```json
{
  "object": "equipment:1e172d76-3433-4ee7-ae1a-9e7d8ae0f12b",
  "changes": {
    "damage": "2d6",
    "weight_kg": 0.5,
    "rarity": "Rare"
  }
}
```

将输入保存为 UTF-8 JSON 后，通过 `--request` 指定文件即可。中文名称不是可靠的唯一标识，必须选择目录返回的完整 `equipment:<UUID>`；本次一次请求修改一个对象，可同时提交多个允许字段。

接口函数同样可被网站后端直接调用：

```python
from scripts.generate_equipment import generate

pak = generate(request, confirmed=True, allow_unverified=True)
```

后端必须在用户确认后才传 `confirmed=True`，参数变化后重新确认。未知对象、不适用字段、重复 JSON 键、非法数值、未确认请求会停止，不产生修改文件。文件名、Stats 标识及本地化句柄来自目录，不接受用户输入原始 Stats 代码。

LSLib 默认位置为 `.tools/lslib/v1.20.4/Packed/Tools/Divine.exe`，可用 `--packager` 改为另一绝对路径。它来自 [Norbyte/lslib v1.20.4](https://github.com/Norbyte/lslib/releases/tag/v1.20.4)，依赖本机 .NET 8。本次没有复制第三方 Python 实现代码。

## 输出和影响范围

每次生成独立 UUID 的目录，位于 `build/equipment-mvp/<UUID>/`，包含 `.pak`、`mod-source`、`unpacked-check`、`result.json`、`使用说明.txt`。清单记录请求、目录哈希、普通及荣誉原值、共用记录的模板、潜在继承子记录、包哈希，以及生成/打包/解包/游戏验证状态。

数值输出采用同名稀疏覆盖，仅写提交字段，例如：

```text
new entry "UND_Duergar_ShortswordOfFirstBlood"
type "Weapon"
using "UND_Duergar_ShortswordOfFirstBlood"
data "Damage" "2d6"
```

此方案延续已经游戏验证的荣誉规则修复，不复制 DefaultBoosts、被动、模型、动画或完整 RootTemplate。只改名时仅输出中文本地化文件和包元数据。

修改会作用于共用 Stats 的所有装备实例，子记录未自行覆盖字段时也可能继承变化。普通长剑等父记录尤其可能影响多把特殊武器；输出 `potential_descendant_records` 表明潜在范围，不代表所有子记录必定改变。`--list` 可以在确认前查看 `shared_record_templates` 和 `descendant_records`。若产品后续要求只改某一模板而不影响同记录对象，需要单独设计 RootTemplate 克隆及引用替换，不属于本版。

同对象的旧测试包应停用，再使用新包；安装后完整重启游戏并重新装备检查。生成器不自动安装、不修改游戏设置或存档。仍由用户将包复制到游戏 Mods 目录并启用。

## 验证证据和剩余工作

本次新增 9 项自动测试，连同原有测试共 40 项通过；测试遍历全部 1,872 个候选，检查字段适用性、最小文件输出、名称 XML 转义、无 DefaultBoosts/被动/RootTemplate 复制，并测试缺失/循环继承、非法输入和确认门槛。这个结果是文件层验证，不是 1,872 次游戏验证。

分别生成第一滴血伤害、第一滴血改名、长剑伤害与双手伤害、躯干防具重量/稀有度、盾牌重量/稀有度、戒指重量/稀有度六个代表包，实际使用 LSLib 打包并重新解包，与源文件逐字节比较通过。记录见 `build/equipment-mvp/verification.json`。全部本次新包的 `game_validation` 仍为 `not_performed`。

此前用户报告第一滴血 2d6、曙光短剑名称、敏捷加成、警觉替换以及治愈真言 36 米已生效。前两项用作本版已知对象/值；其余继续由旧接口提供。本版没有把个别成功外推为新增对象已通过。

下一步由用户选择实际持有的装备，用本版测试包验证：单手与双手伤害骰分别生效、重量及负重更新、稀有度显示、名称显示、原被动和动画保留、共用记录和继承影响范围、停用恢复。组合请求也需要独立回归。

当前完成的是通用校验与生成模块及打包检查，尚未完成网站 API、用户确认界面、全装备游戏验证或执行计划整个部分 3。实际应用技能是 Python 模块封装、结构化 JSON、继承解析、参数校验和自动化检查；用户提供修改目标及历史游戏证据，智能体完成目录构建、通用代码、自动测试与包内容核对。
