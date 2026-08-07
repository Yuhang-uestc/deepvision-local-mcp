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
Write-Host "完成。重启 Codex 后生效。"
