# Local Vision MCP 一键安装：环境检查 →（可选依赖）→ 注册 MCP → 安装 skill
# 用法：
#   基础安装：    powershell -ExecutionPolicy Bypass -File setup.ps1
#   完整安装：    powershell -ExecutionPolicy Bypass -File setup.ps1 -Extras
#   测试用参数：-SkipChecks -ConfigPath <临时配置> -SkillDest <临时目录>
param(
    [switch]$Extras,
    [switch]$SkipChecks,
    [string]$ConfigPath = "",
    [string]$SkillDest = ""
)
$ErrorActionPreference = "Continue"

Write-Host "===== Local Vision MCP 一键安装 ====="

if (-not $SkipChecks) {
    Write-Host "`n[1/5] 检查 Python ..."
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Write-Host "FAIL: 未找到 Python。请先安装 Python 3.9+（https://www.python.org/downloads/）后重试。"
        exit 1
    }
    python --version

    Write-Host "`n[2/5] 检查 Ollama 与视觉模型 ..."
    try {
        ollama list | Out-Null
        $models = (ollama list) -join "`n"
        if ($models -notmatch "qwen3-vl") {
            Write-Host "WARN: 未找到视觉模型 qwen3-vl，运行：ollama pull qwen3-vl:8b"
        } else {
            Write-Host "OK: 视觉模型已就绪"
        }
    } catch {
        Write-Host "WARN: 未检测到 Ollama，请先安装并启动（https://ollama.com）"
    }
} else {
    Write-Host "`n[1/5] 跳过环境检查（-SkipChecks）"
    Write-Host "[2/5] 跳过环境检查（-SkipChecks）"
}

if ($Extras) {
    Write-Host "`n[3/5] 安装可选依赖（PaddleOCR + CLIP，需联网，体积较大）..."
    & (Join-Path $PSScriptRoot "install-extra.ps1")
} else {
    Write-Host "`n[3/5] 跳过可选依赖。如需 PaddleOCR/CLIP，运行 install-extra.ps1 或加 -Extras。"
}

Write-Host "`n[4/5] 注册 local_vision MCP ..."
& (Join-Path $PSScriptRoot "register-mcp.ps1") -ConfigPath $ConfigPath

Write-Host "`n[5/5] 安装 vision-perceive skill ..."
& (Join-Path $PSScriptRoot "install-skill.ps1") -SkillDest $SkillDest

Write-Host "`n===== 安装完成 ====="
Write-Host "下一步：重启 Codex，然后说：分析这张图 C:/某路径/图片.png"
Write-Host "遇问题先跑 check.ps1 自检，或查阅 docs/部署与常见问题.md"
