# 兼容入口：注册 local_vision MCP（等同于 register-mcp.ps1）
# 用法：powershell -ExecutionPolicy Bypass -File install.ps1
& (Join-Path $PSScriptRoot "register-mcp.ps1")
