param([Parameter(Mandatory=$true)][string]$GameData)
# Read game packages, write only to project .tools and build. Never installs a mod.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$divine = Join-Path $projectRoot '.tools/lslib/v1.20.4/Packed/Tools/Divine.exe'
$destination = Join-Path $projectRoot '.tools/v11-assets'
$logs = Join-Path $projectRoot 'build/v1.1'
New-Item -ItemType Directory -Force $logs | Out-Null
function Invoke-Divine([string[]]$Arguments) {
    & $divine @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Divine failed: $LASTEXITCODE" }
}
Invoke-Divine @('-g','bg3','-a','extract-package','-s',"$GameData/Gustav.pak",'-d',$destination,'-x','Mods/Gustav/Globals/WLD_Main_A/Characters/*')
Invoke-Divine @('-g','bg3','-a','extract-package','-s',"$GameData/Gustav.pak",'-d',"$projectRoot/.tools/v11-acquisition",'-x','*TreasureTable*')
Invoke-Divine @('-g','bg3','-a','extract-package','-s',"$GameData/Shared.pak",'-d',$destination,'-x','Public/*/GUI/*.lsx')
Invoke-Divine @('-g','bg3','-a','extract-package','-s',"$GameData/Shared.pak",'-d',$destination,'-x','Public/Shared/Content/Assets/Weapons/*Humans*/*')
Get-ChildItem -LiteralPath $destination -Recurse -Filter '*.lsf' | ForEach-Object {
    Invoke-Divine @('-g','bg3','-a','convert-resource','-s',$_.FullName,'-d',[IO.Path]::ChangeExtension($_.FullName,'lsx'),'-i','lsf','-o','lsx')
}
Copy-Item -LiteralPath "$destination/Mods/Gustav/Globals/WLD_Main_A/Characters/_merged.lsx" -Destination "$destination/characters.lsx"
Invoke-Divine @('-g','bg3','-a','list-package','-s',"$GameData/Icons.pak") | Set-Content "$logs/icons-pak.log" -Encoding utf8
Invoke-Divine @('-g','bg3','-a','list-package','-s',"$GameData/Models.pak",'-x','*Weapons*') | Set-Content "$logs/models-pak.log" -Encoding utf8
