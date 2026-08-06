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

Write-Host "`n完成。装好后重启 Codex 生效。PaddleOCR 首次调用会联网下载识别模型（约 100MB+）。"
