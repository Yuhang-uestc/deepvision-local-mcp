# 安装/更新 vision-perceive skill 到 ~/.codex/skills
# 用法：powershell -ExecutionPolicy Bypass -File install-skill.ps1
# 可选：-SkillDest <路径>（自定义/测试目标目录）
param(
    [string]$SkillDest = ""
)
$ErrorActionPreference = "Stop"

$src = Join-Path $PSScriptRoot "skills\vision-perceive"
if ($SkillDest -eq "") {
    $SkillDest = Join-Path $env:USERPROFILE ".codex\skills\vision-perceive"
}

if (-not (Test-Path -LiteralPath (Join-Path $src "SKILL.md"))) {
    Write-Error "找不到 skill 源：$src"
}
if (Test-Path -LiteralPath $SkillDest) {
    Write-Host "更新 skill → $SkillDest"
    Copy-Item -Path (Join-Path $src '*') -Destination $SkillDest -Recurse -Force
} else {
    New-Item -ItemType Directory -Force (Split-Path $SkillDest) | Out-Null
    Copy-Item -LiteralPath $src -Destination $SkillDest -Recurse
    Write-Host "已安装 skill → $SkillDest"
}

# 注入 call_tool.py 绝对路径（CLI 兜底）：占位符替换成每台机器自己的路径。
# 用 .NET 读写，避免 PowerShell 5.1 对 UTF-8 中文按 GBK 误读。
$skillFile = Join-Path $SkillDest "SKILL.md"
$callTool = Join-Path $PSScriptRoot "call_tool.py"
if (Test-Path -LiteralPath $skillFile) {
    $content = [System.IO.File]::ReadAllText($skillFile, [System.Text.Encoding]::UTF8)
    $callToolToml = $callTool.Replace('\', '/')
    $content = $content.Replace("__CALL_TOOL_PATH__", $callToolToml)
    [System.IO.File]::WriteAllText($skillFile, $content, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "已注入 CLI 路径：$callToolToml"
}

Write-Host "完成。重启 Codex 后生效。"
