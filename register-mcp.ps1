# 注册 local_vision MCP 到 Codex 配置（仅追加，不改现有行；自动备份）。
# 用法：powershell -ExecutionPolicy Bypass -File register-mcp.ps1
# 可选：-ConfigPath <路径>（自定义/测试配置路径）
param(
    [string]$ConfigPath = ""
)
$ErrorActionPreference = "Stop"

$serverPath = Join-Path $PSScriptRoot "server.py"
if ($ConfigPath -eq "") {
    $ConfigPath = Join-Path $env:USERPROFILE ".codex\config.toml"
}

if (-not (Test-Path -LiteralPath $serverPath)) {
    Write-Error "找不到 server.py：$serverPath"
}
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    Write-Error "找不到 Codex 配置文件：$ConfigPath（先启动一次 Codex 让它生成，或手动创建）"
}

$content = Get-Content -LiteralPath $ConfigPath -Raw
if ($content -match '\[mcp_servers\.local_vision\]') {
    Write-Host "local_vision 已注册，无需改动。"
} else {
    $backup = "$ConfigPath.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Copy-Item -LiteralPath $ConfigPath -Destination $backup
    Write-Host "已备份配置：$backup"

    # TOML 路径用正斜杠，避免反斜杠转义问题
    $serverPathToml = $serverPath.Replace('\', '/')
    $block = "`n`n[mcp_servers.local_vision]`ncommand = `"python`"`nargs = [`"$serverPathToml`"]`n"
    [System.IO.File]::AppendAllText($ConfigPath, $block, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "local_vision 已注册（仅追加）。"
}

# 校验：配置文件可正常解析（utf-8-sig 兼容 BOM）
python -c "import tomllib, sys, pathlib; c = tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8-sig')); print('配置解析 OK'); print('mcp_servers:', list(c.get('mcp_servers', {}).keys()))" "$ConfigPath"
if ($LASTEXITCODE -ne 0) { Write-Host "WARN: 配置校验未通过，请检查 $ConfigPath" }
