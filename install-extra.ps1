# 安装可选依赖：PaddleOCR（增强文字识别）、CLIP（YOLOE 零样本检测需要）。
# 用法：powershell -ExecutionPolicy Bypass -File install-extra.ps1
$ErrorActionPreference = "Continue"

Write-Host "===== 1/2 安装 PaddleOCR（场景文字识别，体积较大，约几百 MB）====="
python -m pip install paddlepaddle paddleocr

Write-Host "`n===== 2/2 安装 CLIP（YOLOE 零样本检测的文字编码）====="
python -m pip install git+https://github.com/ultralytics/CLIP.git

Write-Host "`n===== 验证 ====="
python -c "import paddleocr; print('PaddleOCR OK:', paddleocr.__version__)"
if ($LASTEXITCODE -ne 0) { Write-Host 'PaddleOCR 安装未通过验证，请查看上面的报错（注意 Python 3.13 的 wheel 兼容性）。' }
python -c "import clip; print('CLIP OK')"
if ($LASTEXITCODE -ne 0) { Write-Host 'CLIP 安装未通过验证，请查看上面的报错。' }

Write-Host "`n完成。装好后重启 Codex 生效。"
