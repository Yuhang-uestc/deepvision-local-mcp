# 环境自检：确认 Python、Ollama、视觉模型、检测依赖、MCP 注册是否就绪。
# 用法：powershell -ExecutionPolicy Bypass -File check.ps1
$ErrorActionPreference = "Continue"

Write-Host "===== 1) Python ====="
python --version
python -c "import sys; print('OK: python', sys.executable)"

Write-Host "`n===== 2) Ollama ====="
try {
    ollama list
} catch {
    Write-Host "FAIL: 未检测到 Ollama，请先安装并启动（托盘图标常驻）。"
}

Write-Host "`n===== 3) 视觉模型 qwen3-vl:8b ====="
$hasVision = $false
try {
    $models = (ollama list) -join "`n"
    if ($models -match "qwen3-vl") { $hasVision = $true }
} catch {}
if ($hasVision) { Write-Host "OK: 视觉模型已就绪" } else { Write-Host "WARN: 未找到 qwen3-vl 模型，运行: ollama pull qwen3-vl:8b" }

Write-Host "`n===== 4) 检测依赖 (ultralytics / cv2 / Pillow) ====="
python -c "import ultralytics; print('ultralytics', ultralytics.__version__)"
python -c "import cv2; print('cv2', cv2.__version__)"
python -c "import PIL; print('Pillow', PIL.__version__)"

Write-Host "`n===== 5) MCP 注册 (local_vision) ====="
$cfg = Join-Path $env:USERPROFILE ".codex\config.toml"
if (Test-Path -LiteralPath $cfg) {
    $content = Get-Content -LiteralPath $cfg -Raw
    if ($content -match 'local_vision') { Write-Host "OK: local_vision 已注册" } else { Write-Host "FAIL: 未注册，运行 register-mcp.ps1" }
} else {
    Write-Host "FAIL: 找不到 Codex 配置 $cfg"
}

Write-Host "`n===== 6) server.py 语法 ====="
python -m py_compile "$PSScriptRoot\server.py" 2>$null
if ($LASTEXITCODE -eq 0) { Write-Host "OK: server.py 语法正确" } else { Write-Host "FAIL: server.py 语法错误" }
