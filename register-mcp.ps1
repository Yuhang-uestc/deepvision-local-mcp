# 注册 local_vision MCP 到 Codex 配置（安全版，实际逻辑在 register_mcp.py）。
# 重要：运行前请先完全退出 Codex 桌面应用，否则应用可能用旧配置覆盖修改。
# 用法：powershell -ExecutionPolicy Bypass -File register-mcp.ps1
# 可选：-ConfigPath <路径>（自定义/测试配置路径）；-PythonPath <绝对路径>（写入的 Python，默认用当前解释器）
param(
    [string]$ConfigPath = "",
    [string]$PythonPath = ""
)
$ErrorActionPreference = "Stop"

$helper = Join-Path $PSScriptRoot "register_mcp.py"
if (-not (Test-Path -LiteralPath $helper)) {
    Write-Error "找不到 $helper"
}

$helperArgs = @($helper)
if ($ConfigPath -ne "") { $helperArgs += @("--config", $ConfigPath) }
if ($PythonPath -ne "") { $helperArgs += @("--python", $PythonPath) }

python @helperArgs
exit $LASTEXITCODE
