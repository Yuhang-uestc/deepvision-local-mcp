# One-click registration of the local-vision MCP server into ~/.codex/config.toml
# Usage:  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"

$serverPath = "C:/Users/Administrator/Documents/Codex/2026-08-05/pytorch-vision-https-github-com-pytorch/outputs/vision-mcp-local/server.py"
$configPath = Join-Path $env:USERPROFILE ".codex\config.toml"

if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Error "Cannot find Codex config: $configPath"
}
if (-not (Test-Path -LiteralPath $serverPath)) {
    Write-Error "Cannot find server.py: $serverPath"
}

# Backup the original config first
$backup = "$configPath.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $configPath -Destination $backup
Write-Host "Backup saved to: $backup"

$content = Get-Content -LiteralPath $configPath -Raw
if ($content -match '\[mcp_servers\.local_vision\]') {
    Write-Host "local_vision is already registered, nothing to do."
} else {
    $block = "`n`n[mcp_servers.local_vision]`ncommand = `"python`"`nargs = [`"$serverPath`"]`n"
    [System.IO.File]::AppendAllText($configPath, $block, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "local_vision MCP registered."
    Write-Host "Restart Codex, then say: analyze C:/path/to/image.png"
}
