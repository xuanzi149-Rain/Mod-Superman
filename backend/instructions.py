"""Fixed delivery instructions, based on the project's recorded installation path."""
LABELS = {'damage':'基础伤害','versatile_damage':'双手伤害','name':'中文名称','weight_kg':'重量（kg）','rarity':'稀有度'}
RARITIES = {'Common':'普通','Uncommon':'精良','Rare':'稀有','VeryRare':'珍奇','Legendary':'传奇'}


def delivery_instructions(plan, item, filename, game_context):
    changes = '\n'.join(f"- {LABELS[row['field']]}：{RARITIES.get(row['original'], row['original'])} → {RARITIES.get(row['new'], row['new'])}"
                        for row in plan['changes'])
    return f'''Mod-Superman 装备修改使用说明
制作编号：{plan['plan_id']}
对象：{item['display_name']}
PAK 文件：{filename}

本次确认的修改
{changes}

环境与验证状态
目录版本依据：{game_context}
此版本依据来自历史记录，不表示本次已在该版本游戏中验证。
源文件、PAK 创建、解包内容及 ZIP 均经过程序检查；本包安装和游戏验证未执行。

安装与启用（Windows）
1. 退出游戏，保留原存档并准备测试副本。
2. 解压下载的 ZIP。PAK 已由网站打包，不需要再次本地打包。
3. 停用修改同一对象的旧测试包及旧生成包，避免相互覆盖。
4. 将上述 .pak 文件复制到：
   %LOCALAPPDATA%\\Larian Studios\\Baldur's Gate 3\\Mods
5. 启动游戏，在游戏内 Mod 管理界面找到并启用本次 Mod；加载测试副本。

检查效果
重新装备目标装备，逐项核对上述名称、重量、稀有度或伤害骰。
基础伤害与双手伤害分别检查；伤害按公式和战斗日志判断，不按一次攻击的最终数字判断。
只有提交的字段被覆盖；Stats 修改可能影响共用记录及继承该记录的装备，不能保证只改背包中的一个实例。
名称仅覆盖简体中文。未修改售价；其他 Mod、难度和游戏版本可能影响结果。

停用与恢复
在 Mod 管理界面停用本次 Mod，退出并重启游戏，加载修改前的测试存档核对原值。
移除时只处理本次 PAK，不删除其他 Mod 或存档。

已知限制与反馈
{'本方案包含尚待游戏验证的参数或组合，已按试验方案确认。' if plan['experimental'] else '存在历史参考方案，但本次新包仍需独立验证。'}
若没有出现 Mod、无法启用或效果不符，请返回网站反馈，不要把下载成功当作游戏生效。
请提供制作编号、游戏版本、问题阶段、预期与实际效果、其他同对象 Mod 情况。
下载生成后7天有效；请保存 ZIP。反馈是用户报告，与实际观察的游戏验证分别记录。
'''
