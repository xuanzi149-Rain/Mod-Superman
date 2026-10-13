# 第一滴血短剑 Python 复现与验收

本文件记录 v1 复现过程。后续发现 v1 会覆盖荣誉规则的满血附伤配置，已被 v2 精简覆盖方案取代。不要按下面旧版步骤重新发布到游戏；当前操作与回归见《第一滴血短剑荣誉附伤修复.md》。

手工包的游戏截图已显示基础伤害为 2d6，用户报告战斗伤害符合预期。Python 从修改前的两份模板计算 1d6 ×2，分别新增编辑器 Damage 字段和运行文件 Damage 行；已生成的结果与手工 after 文件逐字节一致。重新打包和程序包游戏验证仍待完成。

## 生成与检查

脚本为 `scripts/generate_first_blood.py`，只支持已确认的第一滴血短剑基础伤害两倍方案。模板路径为 `samples/first-blood/before`。程序先核对唯一对象和两份基准文件的 SHA256，再生成；基准改变必须重新核验，不能直接复用旧规则。输出目录必须尚不存在，防止覆盖基准或已有结果。

脚本使用标准库，兼容 Python 3.11。当前终端的 py 启动器登记了不可启动的 Store Python；本轮使用 Codex 内置 Python 3.12.14 完成实际运行，不需要安装额外库。在项目根目录运行：

```powershell
& 'C:\Users\17583\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/generate_first_blood.py --confirmed
```

本轮已经生成默认输出 `build/first-blood/python`。不需要再次执行。若有必要重跑，指定一个尚不存在的新目录，例如增加 `--output build/first-blood/python-rerun`。

输出包括两份修改文件、`manifest.json` 和 `README.txt`；没有自动生成 .pak。清单记录确认参数、模板版本、文件摘要和各阶段状态，不把生成成功当作游戏验收。

5 项 unittest 检查已通过，包括生成结果等于手工样例、未确认拒绝、7 种非法模板子场景、文件缺失拒绝和不覆盖已有输出。运行方式：

```powershell
& 'C:\Users\17583\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

## 接入 Toolkit 并重新打包

先保存并关闭 Toolkit，同时退出游戏，避免编辑器缓存重写文件。before、after 和手工 .pak 留在仓库作为基准。

模块目录为 `FirstBloodDamageTest_fa86e11f-65e1-7489-881e-69cb2b80e055`。复制并替换以下两个文件，游戏根目录使用 Steam“浏览本地文件”定位：

| 程序输出 | 游戏项目目标 |
|---|---|
| build/first-blood/python/editor-stats/Stats/Weapon.stats | Data/Editor/Mods/模块目录/Stats/Stats/Weapon.stats |
| build/first-blood/python/runtime-stats/Generated/Data/Weapon.txt | Data/Public/模块目录/Stats/Generated/Data/Weapon.txt |

重新打开 Toolkit 项目，在 Weapon [FirstBloodDamageTest] 中确认 Damage 为 2d6，保存，再按之前流程 Publish Local。发布包保存到 `build/first-blood/python-pak`，保留默认包文件名。将包复制到游戏 Mods 目录，替换同名手工包；同一模块只保留一份启用的包。使用相同模块是为了对照复现，不创建第二个相互覆盖的 Mod。

保存和发布后，再复制实际游戏项目中的这两份文件到 `samples/first-blood/program-republished`，保留 editor-stats 和 runtime-stats 相对结构。智能体比较与程序输出的差异，以检查是否被编辑器重写。

## 游戏复验与剩余项

重新启用并加载测试档，检查物品与战斗日志的基础骰为 2d6。记录本次游戏版本、难度、包路径和启用 Mod。程序输出与手工输出一致，只证明文件层面的复现，仍需这次实际打包及加载。

手工日志截图含力量加值、3d6 额外穿刺和重掷，不能将总伤害 30 当作纯基础伤害或平均伤害指标。物品截图另外显示 +2 强酸、+1d4 火焰和条件 +1d8 穿刺，其中条件附伤只证实说明保留，还没有独立验证触发。

补测受伤目标普通攻击和满血目标普通攻击，尽量去掉涂毒、额外附伤、偷袭等干扰；同时验证普通短剑未变，以及停用 Mod 后重载原测试档恢复 1d6。保留截图和用户报告。游戏版本尚未核对，不对其他版本承诺兼容。

## 代码参考与技能证据

参考 [BG3-pyUpgrade 的 Stats 读取、写入和目录组织](https://github.com/3Xploitd/BG3-pyUpgrade/blob/main/pyUpgrade.py)。它的 create_upgrades 会改变记录名和附魔，本脚本没有复制其实现或引入其依赖，采用本地手工差异独立实现。无需为复制代码添加第三方许可证声明；若以后复制代码，再核对许可证和提交版本。

用户完成了 Toolkit 覆盖、手工修改、打包、安装和游戏测试，并提供模板与截图。智能体完成字段核对、文件对比、Python 生成、异常检查与记录整理。这一阶段实际应用了技术可行性分析、AI 辅助开发、结构化文件处理和问题定位。网站、模型 API、技能样例及完整部分 1 验收尚未完成。
