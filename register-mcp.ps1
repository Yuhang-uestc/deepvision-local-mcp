# 仅追加 local_vision MCP 注册，绝不改动配置文件中的任何现有行。
# 用法：powershell -ExecutionPolicy Bypass -File register-mcp.ps1
$ErrorActionPreference = "Stop"

$serverPath = "C:/Users/Administrator/Documents/Codex/2026-08-05/pytorch-vision-https-github-com-pytorch/outputs/vision-mcp-local/server.py"
$configPath = Join-Path $env:USERPROFILE ".codex\config.toml"

if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Error "Cannot find Codex config: $configPath"
}
if (-not (Test-Path -LiteralPath $serverPath)) {
    Write-Error "Cannot find server.py: $serverPath"
}

$content = Get-Content -LiteralPath $configPath -Raw
if ($content -match '\[mcp_servers\.local_vision\]') {
    Write-Host "local_vision is already registered. Nothing changed."
} else {
    $backup = "$configPath.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Copy-Item -LiteralPath $configPath -Destination $backup
    Write-Host "Backup saved: $backup"

    # 只在文件末尾追加，不修改任何现有行
    $block = "`n`n[mcp_servers.local_vision]`ncommand = `"python`"`nargs = [`"$serverPath`"]`n"
    [System.IO.File]::AppendAllText($configPath, $block, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "local_vision registered (append-only)."
}

# 校验：配置文件可正常解析，且 DeepSeek 相关配置完好
python -c "import tomllib, os, pathlib; c = tomllib.loads(pathlib.Path(os.path.expanduser('~/.codex/config.toml')).read_text(encoding='utf-8-sig')); print('mcp_servers:', list(c.get('mcp_servers', {}).keys())); print('deepseek provider intact:', 'deepseek' in c.get('model_providers', {})); print('current model:', c.get('model'))"
