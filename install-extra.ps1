# 安装可选依赖：PaddleOCR（增强文字识别）、CLIP（YOLOE 零样本检测需要）。
# 用法：powershell -ExecutionPolicy Bypass -File install-extra.ps1
$ErrorActionPreference = "Continue"

Write-Host "===== 1/2 安装 PaddleOCR（场景文字识别，体积较大，约几百 MB）====="
python -m pip install paddlepaddle paddleocr

Write-Host "`n===== 2/2 安装 CLIP（YOLOE 零样本检测的文字编码）====="
Write-Host "注意：ultralytics 的 YOLOE 需要带 truncate 参数的 CLIP fork（PyPI 版 openai clip 不兼容），"
Write-Host "GitHub 直连失败时会自动尝试镜像代理。"

$clipInstalled = $false
$sources = @(
    "git+https://github.com/ultralytics/CLIP.git",
    "git+https://ghproxy.net/https://github.com/ultralytics/CLIP.git",
    "git+https://ghfast.top/https://github.com/ultralytics/CLIP.git"
)
foreach ($src in $sources) {
    if ($clipInstalled) { break }
    Write-Host ("`n尝试来源: " + $src)
    python -m pip install $src
    if ($LASTEXITCODE -eq 0) { $clipInstalled = $true }
}

if (-not $clipInstalled) {
    Write-Host "`n所有 GitHub 来源均不可达。最后尝试 PyPI 的 openai clip（API 可能不兼容，见下方验证结果）。"
    python -m pip install clip
    if ($LASTEXITCODE -eq 0) { $clipInstalled = $true }
}

Write-Host "`n===== 验证 ====="
python -c "import paddleocr; print('PaddleOCR OK:', paddleocr.__version__)"
if ($LASTEXITCODE -ne 0) { Write-Host 'PaddleOCR 安装未通过验证，请查看上面的报错（注意 Python 3.13 的 wheel 兼容性）。' }

if ($clipInstalled) {
    python -c "import clip, inspect; print('CLIP import OK; tokenize 支持 truncate:', 'truncate' in inspect.signature(clip.tokenize).parameters)"
} else {
    Write-Host "CLIP 安装失败。稍后可手动重试，或换其他 GitHub 镜像源，例如："
    Write-Host "  python -m pip install git+https://ghproxy.net/https://github.com/ultralytics/CLIP.git"
}

# ===== 预下载 PaddleOCR 模型到项目缓存（终端与 AI 会话共用，避免重复下载）=====
Write-Host "`n===== 预下载 PaddleOCR 模型（一次性，约 100MB+）====="
$cacheDir = Join-Path $PSScriptRoot "outputs\paddlex_cache"
New-Item -ItemType Directory -Force $cacheDir | Out-Null
$env:PADDLE_PDX_CACHE_HOME = $cacheDir
Push-Location $PSScriptRoot
python -c "import sys; sys.path.insert(0, '.'); import server; server._get_paddle_ocr('zh'); print('OK: PaddleOCR 模型已就绪')"
$dlOk = ($LASTEXITCODE -eq 0)
Pop-Location

if ($dlOk) {
    setx PADDLE_PDX_CACHE_HOME $cacheDir | Out-Null
    Write-Host "模型缓存：$cacheDir"
    Write-Host "已设置用户环境变量 PADDLE_PDX_CACHE_HOME（终端与 AI 会话共用，重启终端/Codex 后生效）。"
    Write-Host "注意：缓存跟随项目目录；项目移动/重命名后需重新运行本脚本或手动更新该环境变量。"
} else {
    Write-Host "WARN: 模型预下载未完成（可能网络受限）。未设置环境变量——终端首次调用会在默认位置下载；"
    Write-Host "想让终端与 AI 会话共用同一份缓存，请网络正常后重新运行本脚本。"
}

Write-Host "`n完成。装好后重启 Codex 生效。"
