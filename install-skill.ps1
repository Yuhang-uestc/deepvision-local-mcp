# 安装/更新 vision-perceive skill 到 ~/.codex/skills，并安装全局 AGENTS.md（本机识图工具入口）。
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

# 安装/更新全局 AGENTS.md（本机识图工具入口，仅图片任务相关，不影响其它任务）。
# 用标记块替换，保留用户已有的其它内容；可重复执行。
$agentsDest = Join-Path $env:USERPROFILE ".codex\AGENTS.md"
$agentsTemplate = Join-Path $PSScriptRoot "AGENTS.global.template.md"
if (Test-Path -LiteralPath $agentsTemplate) {
    $block = [System.IO.File]::ReadAllText($agentsTemplate, [System.Text.Encoding]::UTF8)
    $block = $block.Replace("__CALL_TOOL_PATH__", $callToolToml)
    $existing = ""
    if (Test-Path -LiteralPath $agentsDest) {
        $existing = [System.IO.File]::ReadAllText($agentsDest, [System.Text.Encoding]::UTF8)
    }
    $markerStart = "<!-- deepvision-local-mcp:start -->"
    $markerEnd = "<!-- deepvision-local-mcp:end -->"
    $startIdx = $existing.IndexOf($markerStart)
    $endIdx = $existing.IndexOf($markerEnd)
    if ($startIdx -ge 0 -and $endIdx -gt $startIdx) {
        $existing = $existing.Substring(0, $startIdx) + $block.Trim() + $existing.Substring($endIdx + $markerEnd.Length)
    } else {
        if ($existing.Trim() -ne "") {
            $existing = $existing.TrimEnd() + "`r`n`r`n"
        }
        $existing = $existing + $block
    }
    [System.IO.File]::WriteAllText($agentsDest, $existing, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "已安装全局 AGENTS.md → $agentsDest"
}

Write-Host "完成。重启 Codex 后生效。"
