# 一键安装 vision-perceive skill 到 ~/.codex/skills
# 用法：powershell -ExecutionPolicy Bypass -File install-skill.ps1
$ErrorActionPreference = "Stop"

$src = "C:/Users/Administrator/Documents/Codex/2026-08-05/pytorch-vision-https-github-com-pytorch/outputs/vision-mcp-local/skills/vision-perceive"
$dest = Join-Path $env:USERPROFILE ".codex\skills\vision-perceive"

if (-not (Test-Path -LiteralPath "$src\SKILL.md")) {
    Write-Error "Cannot find skill source: $src"
}
if (Test-Path -LiteralPath $dest) {
    Write-Host "Updating existing vision-perceive skill at $dest ..."
    Copy-Item -Path (Join-Path $src '*') -Destination $dest -Recurse -Force
    Write-Host "Skill updated."
} else {
    Copy-Item -LiteralPath $src -Destination $dest -Recurse
    Write-Host "Installed vision-perceive skill to $dest"
}

Write-Host ""
Write-Host "Next: restart Codex. The skill will be available from the next conversation turn."
