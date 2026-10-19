# Mod-Superman

辅助制作《博德之门 3》装备 Mod 的本地网站。选择修改已有装备或创建新装备，用自然语言描述需求，查看程序解析出的实际效果，确认方案后生成可下载的 Mod 包。

AI 负责理解与澄清，Python 程序负责参数、资源和依赖校验，以及文件生成、打包和解包检查。使用原生 Stats、Passive、Status、Spell 和模板机制，复用游戏美术资源，不依赖 Script Extender 或运行时 Lua。

> **首次使用请先读：本项目目前是需要自行准备游戏资源的本地开发版本，不是 clone 后即可直接使用的在线服务。** GitHub 不包含 `.tools/` 中的完整游戏资源、LSLib、模型密钥和运行数据库。打开网页不等于资源已准备完成。下述 Windows 配置步骤根据项目代码整理；尚未在全新电脑上完成从零安装验收。公开部署和逐项游戏实测仍未完成。

## 使用前需要准备什么

| 项目 | 用途 |
| --- | --- |
| Windows、PowerShell、Git | 当前本地操作环境；本文命令在 PowerShell 中执行 |
| Python 3.12 | 项目已有运行记录使用的版本；其他版本未逐一验证 |
| 已安装的《博德之门 3》及其 `Data` 目录 | 提取本机原生资源，用于对象、技能、外观和依赖校验 |
| LSLib v1.20.4 与 .NET 8 x64 运行时 | 读取游戏资源、转换格式、生成和检查 PAK |
| 自己的百炼或 DeepSeek API 配置 | 自然语言解析；模型调用消耗服务商额度 |

无需安装 Node.js 来运行网站，前端是由 Python 服务提供的 HTML/CSS/JavaScript。Node.js 仅用于可选的前端测试。也无需安装 Codex。

## 1. 克隆项目并安装 Python 依赖

```powershell
git clone https://github.com/xuanzi149-Rain/Mod-Superman.git
cd Mod-Superman

# 将虚拟环境放入已被 Git 忽略的 .runtime 目录。
py -3.12 -m venv .runtime/venv
$pythonExe = (Resolve-Path .runtime/venv/Scripts/python.exe).Path
& $pythonExe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请先解决安装错误。' }
```

后续命令均在项目根目录执行。关闭 PowerShell 后重新操作时，先回到项目目录，并重新设置 `$pythonExe`。不需要激活虚拟环境，也不需要修改系统执行策略。

## 2. 安装打包工具

从 [LSLib v1.20.4 官方发布页](https://github.com/Norbyte/lslib/releases/tag/v1.20.4) 下载 `ExportTool-v1.20.4.zip`，按发布页要求安装 .NET 8 x64 运行时。

将压缩包解压到项目 `.tools/lslib/v1.20.4/`，最终必须存在：

```text
.tools/lslib/v1.20.4/Packed/Tools/Divine.exe
```

检查路径，避免多解压出一层同名目录：

```powershell
$divine = Join-Path (Get-Location) '.tools/lslib/v1.20.4/Packed/Tools/Divine.exe'
if (-not (Test-Path -LiteralPath $divine)) { throw '请先按目录要求安装 LSLib。' }
& $divine --help
```

如果提示缺少 .NET，请先安装运行时再继续。下面的资源准备脚本使用此固定路径。

## 3. 准备本机游戏资源（首次使用必做）

1.1 的资源索引与外观审核结果未随 Git 分发，需要在自己的游戏文件上生成。不能用空 JSON 代替索引，也不能仅复制别人的索引而缺少它记录的源文件：程序会核对源文件摘要。

### 3.1 提取 Stats、RootTemplates 和中文文本

先找到游戏安装目录的 `Data` 文件夹。例如 Steam 安装可能位于 `D:\SteamLibrary\steamapps\common\Baldurs Gate 3\Data`；请替换成自己的实际路径。以下操作读取游戏包，输出到项目 `.tools/`，不会安装 Mod。

在同一个 PowerShell 窗口执行：

```powershell
$gameData = 'D:\SteamLibrary\steamapps\common\Baldurs Gate 3\Data'
$projectRoot = (Get-Location).Path
$divine = Join-Path $projectRoot '.tools/lslib/v1.20.4/Packed/Tools/Divine.exe'
$ErrorActionPreference = 'Stop'

function Invoke-ResourceTool([string[]]$ToolArgs) {
    & $divine -g bg3 @ToolArgs
    if ($LASTEXITCODE -ne 0) { throw "资源工具执行失败：$LASTEXITCODE" }
}

$sources = @(
    @{ Package = 'Shared'; Stats = 'equipment-shared' },
    @{ Package = 'Gustav'; Stats = 'healing-word-Gustav' },
    @{ Package = 'GustavX'; Stats = 'healing-word-GustavX' }
)

foreach ($source in $sources) {
    $pak = Join-Path $gameData ($source.Package + '.pak')
    if (-not (Test-Path -LiteralPath $pak)) { throw "找不到游戏包：$pak" }
    $statsDir = Join-Path $projectRoot ('.tools/' + $source.Stats)
    $rootsDir = Join-Path $projectRoot ('.tools/equipment-roots-' + $source.Package)
    Invoke-ResourceTool @('-a', 'extract-package', '-s', $pak, '-d', $statsDir, '-x', 'Public/*/Stats/Generated/Data/*.txt')
    Invoke-ResourceTool @('-a', 'extract-package', '-s', $pak, '-d', $rootsDir, '-x', 'Public/*/RootTemplates/*')
    Get-ChildItem -LiteralPath $rootsDir -Recurse -Filter '*.lsf' | ForEach-Object {
        Invoke-ResourceTool @('-a', 'convert-resource', '-s', $_.FullName,
            '-d', [IO.Path]::ChangeExtension($_.FullName, 'lsx'), '-i', 'lsf', '-o', 'lsx')
    }
}

$chinesePak = Join-Path $gameData 'Localization/Chinese.pak'
if (-not (Test-Path -LiteralPath $chinesePak)) { throw '未找到中文语言包，请核对游戏语言资源安装位置。' }
$languageDir = Join-Path $projectRoot '.tools/readme-localization'
Invoke-ResourceTool @('-a', 'extract-package', '-s', $chinesePak, '-d', $languageDir, '-x', '*chinese.loca')
$locaFiles = @(Get-ChildItem -LiteralPath $languageDir -Recurse -Filter 'chinese.loca')
if ($locaFiles.Count -ne 1) { throw '中文资源数量不符合预期，请核对语言包内容。' }
Invoke-ResourceTool @('-a', 'convert-loca', '-s', $locaFiles[0].FullName,
    '-d', (Join-Path $projectRoot '.tools/equipment-chinese.xml'))
```

这些目录名沿用了早期实验名称，例如 `healing-word-Gustav`，请保留名称。索引代码按这些位置查找资源。不同游戏版本的文件布局可能不同；若工具没有提取到文件，先检查包内容，不要跳过缺失项继续生成。

### 3.2 建立资源索引与外观审核

依次执行；每条命令成功后再执行下一条。首次提取和审核可能耗时较长。

```powershell
# 图标、武器外观、达蒙获取入口及模型文件清单
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_resource_assets_v11.ps1 -GameData $gameData
if ($LASTEXITCODE -ne 0) { throw '资源准备失败。' }

# 建立 1.1 资源索引
& $pythonExe -m scripts.resource_catalog_v11
if ($LASTEXITCODE -ne 0) { throw '资源索引生成失败。' }

# 扩充身体/装备外观、标签、动作资源并生成审核结果
& $pythonExe -m scripts.prepare_body_assets_v11 --game-data $gameData
if ($LASTEXITCODE -ne 0) { throw '外观资源准备失败。' }
& $pythonExe -m scripts.body_template_audit_v11
if ($LASTEXITCODE -ne 0) { throw '外观审核失败。' }
```

至少应产生：

```text
.tools/equipment-chinese.xml
build/v1.1/resource-catalog.json
build/v1.1/body-template-audit.json
```

此外，索引引用的 `.tools/` 源文件及 `build/v1.1/` 中的模型、图标清单也必须保留。资源目录“生成成功”不代表所有对象都可用，具体对象和组合仍由程序校验。

仓库附带的 `data/equipment_catalog.json`、装备标签和预览是已有环境的快照。如需与自己的游戏资源重新对齐，可在资源准备完成后执行：

```powershell
& $pythonExe -m scripts.equipment_catalog
& $pythonExe -m scripts.export_equipment_labels
& $pythonExe -m scripts.export_equipment_preview
```

每条命令均应成功。它们会更新已跟踪的数据文件，`git status` 出现相应改动是预期现象。游戏更新后应重新提取、建立索引和审核，并重新创建方案；不要在服务运行时替换资源。

## 4. 配置自己的模型 API

```powershell
Copy-Item .env.example .env.local
notepad .env.local
```

仅在首次配置时复制，避免覆盖已有密钥。示例默认使用百炼 Token Plan，北京端点：

```dotenv
MODEL_PROVIDER=bailian
MODEL_NAME=qwen3.7-plus
MODEL_BASE_URL=https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
MODEL_USE_SYSTEM_PROXY=0
BAILIAN_TOKEN_PLAN_API_KEY=填写你自己的Token_Plan专用密钥
```

这是仓库的配置示例，不保证你的账户拥有该模型或套餐权限；模型名、端点和密钥必须与自己的服务商账户匹配。百炼普通按量接口使用 `DASHSCOPE_API_KEY`，不能把普通密钥当作 Token Plan 专用密钥。DeepSeek 的配置方式见代码支持的变量和[模型接入说明](docs/百炼模型接入.md)。

`.env.local` 已被 Git 忽略。密钥只在后端读取，不要填写到网页脚本或提交到 GitHub。系统环境变量优先于 `.env.local`；配置修改后重启服务。没有可用密钥时，模型相关操作会失败，不会自动改用免费模型。

## 5. 启动网站

推荐显式指定自己的 Python，避免启动脚本自动选到其他环境：

```powershell
$pythonExe = (Resolve-Path .runtime/venv/Scripts/python.exe).Path
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_backend.ps1 -Python $pythonExe -Port 8000
```

保留终端运行，在浏览器访问：

- 网站：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 基础健康检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

端口占用时把 `-Port 8000` 改为 `-Port 8016`，浏览器地址也相应修改。按 `Ctrl+C` 停止服务。不要双击 `web/index.html`，完整功能依赖后端接口。

健康检查只能确认服务可响应。要确认 1.1 资源加载成功，还应访问 [装备目录接口](http://127.0.0.1:8000/api/v11/catalog?kind=equipment&limit=1)，检查返回的是装备列表而不是 500 错误。

默认只监听本机，使用单进程运行。仓库的 Dockerfile / Render 配置尚未完成当前 1.1 从零部署验证，不能直接当作已可用的云端安装方案。

## 6. 完成一次制作

1. 选择“修改已有装备”或“创建新装备”，再选择基础装备。新装备还需要通过外观、依赖和获取入口检查。
2. 描述明确需求，例如“把基础伤害改为 2d6，重量设为 0.5 千克”。根据页面提示补充信息。
3. 查看实际参数和效果，检查是否符合预期。自定义文字与实际机制应分别理解，文字本身不会改变机制；不要仅凭名称或描述判断生效内容。
4. 确认当前方案，再生成。参数变化后需要重新确认。具体文案操作以所检出版本的页面为准，历史版本与后续交互规则可能不同。
5. 等待后台生成、打包和解包检查完成，下载 ZIP。ZIP 包含 PAK、修改清单和使用说明；已完成打包，无需自行再次封装 PAK。
6. 按该包的使用说明安装、启用和检查效果，再提交反馈。新装备的获取条件也以包内说明为准。

文件检查、打包成功、用户反馈和实际游戏验证分别记录。候选可选择、成功下载或自动测试通过，都不代表该组合已经在游戏中验证。

## 数据保存与再次使用

启动脚本默认将本地记录保存到 `build/backend/mvp-local/`，包含 SQLite 数据库、会话、任务和下载产物。浏览器 Cookie 用于访问归属；清除 Cookie 或换浏览器后，不能只凭制作编号取回原记录。

需要备份时，先停止服务，再备份完整数据目录。不要只保存 ZIP 或只复制单个数据库文件。项目有产物清理逻辑，重要下载包应另行保存。

更新代码前先运行 `git status` 并保留自己的修改，再执行 `git pull --ff-only`。依赖变化后重新安装 `requirements.txt`；资源格式变化后按文档重建。旧草稿不保证兼容新版本，遇到版本冲突请重新创建并确认方案。

## 常见问题

| 现象 | 检查方式 |
| --- | --- |
| `No module named ...` | 确认安装依赖和启动服务使用同一个 `$pythonExe`；重新执行依赖安装命令 |
| 首页打开，但装备加载失败 | 查看终端错误和 `/api/v11/catalog`；优先检查中文文本、资源索引及其引用文件 |
| 缺少 `resource-catalog.json` | 完成第 3 步，不能仅运行网站启动脚本 |
| `Resource source changed` / `Body audit source changed` | 停止服务，核对资源来源，按依赖顺序重建索引和外观审核，再创建新方案 |
| 找不到 `Divine.exe` 或缺少 .NET | 核对第 2 步的完整路径与运行时 |
| 模型未配置、鉴权失败或超时 | 核对 `.env.local`、系统环境变量、密钥类型、模型权限和网络；参见[调用排查](docs/DeepSeek调用排查与恢复.md) |
| 新建装备候选少或组合被拒绝 | 查看程序给出的具体资源/依赖缺口，不要绕过校验；当前不是任意装备和任意效果都能生成 |
| 网页正常但不确定 Mod 是否生效 | 按下载包说明在游戏内验证；网页的成功状态仅表示对应程序阶段通过 |

## 开发与验证

准备好资源后，可在项目根目录运行本地回归：

```powershell
& $pythonExe -m unittest discover -s tests -v
```

测试包含资源扫描和真实本地打包，可能需要较长时间，并会产生测试文件；部分检查会更新验证记录。不要将测试进程当作网站启动命令。真实模型评测脚本属于另一步操作，会消耗 API 额度。

如已安装 Node.js，可运行现有前端检查：

```powershell
node --test web/model.test.cjs web/craft-feedback.test.cjs tests/test_result_items.js
node --check web/craft.js
```

项目结构及进一步阅读：

| 路径 | 内容 |
| --- | --- |
| `web/` | 网站页面、交互和装备预览 |
| `backend/` | API、AI 解析、方案工作流与存储 |
| `scripts/` | 资源准备、固定编译、打包及验收脚本 |
| `data/`、`prompts/` | 支持目录、结构化协议和 Prompt |
| `tests/` | 自动检查 |
| [1.1 执行计划](1.1版本项目执行计划.md) / [PRD](docs/PRD.md) | 当前范围与产品规则 |
| [阶段 C 执行记录](docs/v1.1/阶段C执行记录.md) | 已完成工作、验证证据和剩余边界 |

本仓库同时保留 1.0 历史样例。遇到历史文档与现行规则不一致时，以当前版本的执行计划、PRD 第 0 节及后续更新记录为准。
