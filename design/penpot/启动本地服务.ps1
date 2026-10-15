$penpotWorking = 'C:/Users/17583/AppData/Local/npm-cache/_npx/3c82a6444c262e31/node_modules/@penpot/mcp'
if (!(Test-Path -LiteralPath $penpotWorking)) { throw '本机 Penpot MCP 安装包不存在，请重新安装官方 @penpot/mcp。' }
Push-Location $penpotWorking
try { & corepack pnpm run start } finally { Pop-Location }
# 同时启动已构建的插件和MCP服务；保持终端运行，然后在Penpot插件中连接。
