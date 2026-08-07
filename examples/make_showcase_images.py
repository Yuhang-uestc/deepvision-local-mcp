# -*- coding: utf-8 -*-
"""生成项目展示图：demo_annotated / social_preview / architecture。

用法：python examples/make_showcase_images.py
说明：demo_annotated 复用 server.py 的真实工具输出（cv_locate 颜色定位 + Windows OCR 文字）。
"""

import math
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server  # 复用真实工具逻辑

EXAMPLES = ROOT / "examples"
EXAMPLES.mkdir(exist_ok=True)

FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_REG = r"C:\Windows\Fonts\msyh.ttc"


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap_text(draw, text, fnt, max_w):
    lines = []
    cur = ""
    for ch in text:
        if draw.textlength(cur + ch, font=fnt) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def draw_arrow(draw, x1, y1, x2, y2, color, width=4):
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    ang = math.atan2(y2 - y1, x2 - x1)
    L = 14
    for da in (0.35, -0.35):
        px = x2 - L * math.cos(ang + da)
        py = y2 - L * math.sin(ang + da)
        draw.polygon(
            [
                (x2, y2),
                (px - L * math.cos(ang) * 0.5, py - L * math.sin(ang) * 0.5),
                (px, py),
            ],
            fill=color,
        )


# ============ 1. 真实工具输出演示 ============
test_img = str(ROOT / "test_image.png")
cv = server.call_cv_locate(
    {"file_path": test_img, "mode": "color", "color": "#3b6ea5", "tolerance": 60}
)
cv_text = cv["content"][0]["text"]
regions = [
    (int(a), int(b), int(c), int(e))
    for a, b, c, e in re.findall(r"区域\d+：像素框 \[(\d+),(\d+),(\d+),(\d+)\]", cv_text)
]

ocr = server._call_windows_ocr(test_img, "zh-Hans-CN")
ocr_text = ocr["content"][0]["text"]
ocr_body = ocr_text.split("文本块位置：")[0]
if ocr_body.startswith("[安全提示]"):
    ocr_body = ocr_body.split("\n\n", 1)[1] if "\n\n" in ocr_body else ocr_body
ocr_lines = [ln for ln in ocr_body.splitlines()[1:] if ln.strip()]

src = Image.open(test_img).convert("RGB")
W, H = src.size
panel_w = 400
canvas = Image.new("RGB", (W + panel_w, H), (15, 23, 42))
canvas.paste(src, (0, 0))
d = ImageDraw.Draw(canvas)

for x1, y1, x2, y2 in regions:
    d.rectangle([x1, y1, x2, y2], outline="#00e5ff", width=3)
    d.rectangle([x1 - 3, y1 - 3, x2 + 3, y2 + 3], outline="#00e5ff", width=1)

px = W + 24
f_title = font(FONT_BOLD, 24)
f_sub = font(FONT_BOLD, 17)
f_body = font(FONT_REG, 16)
f_small = font(FONT_REG, 14)
d.text((px, 18), "工具输出演示（真实调用）", font=f_title, fill="#ffffff")
d.text((px, 56), "① 颜色定位 cv_locate", font=f_sub, fill="#00e5ff")
y = 84
for i, (a, b, c, e) in enumerate(regions, 1):
    d.text((px, y), f"区域{i}  [{a},{b},{c},{e}]", font=f_small, fill="#cbd5e1")
    y += 26
y += 8
d.text((px, y), "② OCR 文字（Windows OCR）", font=f_sub, fill="#4ade80")
y += 30
for ln in ocr_lines[:10]:
    for wrapped in wrap_text(d, ln, f_body, panel_w - 40):
        if y > H - 70:
            break
        d.text((px, y), wrapped, font=f_body, fill="#e2e8f0")
        y += 24
    if y > H - 70:
        break
d.text((px, H - 46), "合成测试图 · 图片仅在本机处理", font=f_small, fill="#64748b")
demo_out = EXAMPLES / "demo_annotated.png"
canvas.save(demo_out)
print("saved", demo_out, canvas.size)

# ============ 2. GitHub 社交横幅 1200x630 ============
BW, BH = 1200, 630
img = Image.new("RGB", (BW, BH), (15, 23, 42))
d = ImageDraw.Draw(img)
for y in range(BH):
    t = y / BH
    d.line(
        [(0, y), (BW, y)],
        fill=(int(15 + 25 * t), int(23 + 34 * t), int(42 + 55 * t)),
    )
eye_cx, eye_cy, eye_r = 1000, 150, 78
d.ellipse(
    [eye_cx - eye_r, eye_cy - eye_r, eye_cx + eye_r, eye_cy + eye_r], fill="#2d4a8f"
)
d.ellipse([eye_cx - 34, eye_cy - 22, eye_cx + 34, eye_cy + 22], outline="#ffffff", width=7)
d.ellipse([eye_cx - 12, eye_cy - 12, eye_cx + 12, eye_cy + 12], fill="#ffffff")
for dx, dy, r in [(180, 90, 4), (240, 180, 3), (150, 300, 5), (700, 520, 4), (830, 560, 3)]:
    d.ellipse([dx - r, dy - r, dx + r, dy + r], fill="#3b82f6")

f_tag = font(FONT_BOLD, 30)
f_title = font(FONT_BOLD, 84)
f_sub = font(FONT_REG, 38)
f_chip = font(FONT_BOLD, 26)
f_url = font(FONT_REG, 24)

d.text((70, 64), "LOCAL VISION MCP · 本地识图", font=f_tag, fill="#38bdf8")
d.text((70, 120), "给 DeepSeek 装上", font=f_title, fill="#ffffff")
d.text((70, 232), "本地眼睛", font=f_title, fill="#ffffff")
d.text((70, 344), "OCR · 检测 · 分割 · 零样本 · 定位 · 裁切放大", font=f_sub, fill="#cbd5e1")
d.text((70, 400), "图片全程不出本机，100% 本地免费", font=f_sub, fill="#7dd3fc")

chips = ["11 个工具", "21 项离线测试", "相同图片缓存秒回", "多轮闭环防幻觉"]
cx, cy = 70, 492
for chip in chips:
    tw = d.textlength(chip, font=f_chip)
    d.rounded_rectangle(
        [cx, cy, cx + tw + 36, cy + 54], radius=27, fill="#1e3a5f", outline="#3b82f6", width=2
    )
    d.text((cx + 18, cy + 10), chip, font=f_chip, fill="#e2e8f0")
    cx += tw + 56
d.text((70, 574), "github.com/Yuhang-uestc/deepvision-local-mcp", font=f_url, fill="#94a3b8")
banner_out = EXAMPLES / "social_preview.png"
img.save(banner_out)
print("saved", banner_out, img.size)

# ============ 3. 架构流程图 ============
AW, AH = 1160, 660
bg = Image.new("RGB", (AW, AH), (15, 23, 42))
d = ImageDraw.Draw(bg)
f_h = font(FONT_BOLD, 30)
f_b = font(FONT_BOLD, 20)
f_s = font(FONT_REG, 17)


def box(x, y, w, h, title, lines, accent):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill="#1e293b", outline=accent, width=2)
    d.text((x + 18, y + 14), title, font=f_b, fill=accent)
    yy = y + 48
    for ln in lines:
        for wl in wrap_text(d, ln, f_s, w - 30):
            d.text((x + 18, yy), wl, font=f_s, fill="#cbd5e1")
            yy += 24


box(50, 210, 260, 240, "MCP 客户端", ["Codex / Claude Code", "Cursor / Trae / opencode", "", "纯文本主模型", "DeepSeek 等"], "#7dd3fc")
box(380, 70, 300, 170, "vision-perceive skill", ["快速/详细模式决策", "多轮识图闭环", "概览→聚焦→交叉校验"], "#fbbf24")
box(760, 70, 340, 170, "server.py · MCP stdio", ["11 个工具：描述 / OCR / 检测", "/ 分割 / 零样本 / 定位 / 裁切", "/ 画框 / 信息 / 模型 / 状态"], "#38bdf8")
draw_arrow(d, 310, 260, 380, 135, "#475569")
draw_arrow(d, 680, 150, 760, 150, "#475569")

engines = [
    ("Ollama", ["qwen3-vl:8b / 4b", "本地视觉模型"], "#4ade80"),
    ("PaddleOCR", ["场景文字识别", "回退 Windows OCR"], "#a78bfa"),
    ("YOLOv8", ["检测 / 分割", "COCO 80 类 + 掩膜"], "#f472b6"),
    ("YOLOE / World", ["零样本检测", "文字找任意物体"], "#fb923c"),
    ("OpenCV / Pillow", ["颜色/模板定位", "裁切 / 画框"], "#22d3ee"),
]
ew, gap = 200, 26
ex0 = (AW - (5 * ew + 4 * gap)) // 2
ey = 400
for i, (t, ls, ac) in enumerate(engines):
    x = ex0 + i * (ew + gap)
    box(x, ey, ew, 150, t, ls, ac)
    draw_arrow(d, 930, 240, x + ew // 2, 400, "#334155", width=3)

d.rounded_rectangle([50, 590, AW - 50, 634], radius=12, fill="#0f172a", outline="#334155", width=1)
d.text(
    (70, 604),
    "图片全程只在本机处理：主模型负责想，本地引擎负责看，MCP 是桥，skill 是流程。",
    font=f_s,
    fill="#94a3b8",
)
arch_out = EXAMPLES / "architecture.png"
bg.save(arch_out)
print("saved", arch_out, bg.size)
