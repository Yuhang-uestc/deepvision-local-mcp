# -*- coding: utf-8 -*-
"""生成项目展示图：demo_input / demo_annotated / social_preview / architecture。

用法：python examples/make_showcase_images.py

说明：
- demo_annotated 复用 server.py 的真实工具输出：cv_locate 颜色定位 + 文字识别。
- 文字识别自动优先 PaddleOCR（本项目的旗舰 OCR），PaddleOCR 不可用时回退
  Windows OCR，并在图上如实标注所用引擎。
- 本机装好 PaddleOCR 后重跑本脚本，即可生成 PaddleOCR 版演示图。
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


# ============ 0. 合成示例图（无任何真实数据） ============
def make_demo_input():
    W, H = 960, 600
    img = Image.new("RGB", (W, H), "#f8fafc")
    d = ImageDraw.Draw(img)
    # 水体（左下）
    d.polygon([(0, 420), (330, 400), (450, 600), (0, 600)], fill="#38bdf8")
    # 农田（右上区域）
    d.rectangle([340, 150, 470, 280], fill="#86efac", outline="#4ade80", width=2)
    d.rectangle([500, 230, 630, 350], fill="#4ade80", outline="#22c55e", width=2)
    d.rectangle([660, 120, 810, 240], fill="#a7f3d0", outline="#4ade80", width=2)
    # 道路（斜向灰色带）
    d.polygon([(455, 0), (525, 0), (610, 600), (535, 600)], fill="#94a3b8")
    # 建筑（右下小方块群）
    for bx, by in [(700, 380), (760, 350), (820, 400), (720, 470), (800, 500), (870, 460)]:
        d.rounded_rectangle([bx, by, bx + 48, by + 42], radius=4, fill="#cbd5e1", outline="#64748b", width=2)
    # 图例框
    d.rounded_rectangle([740, 36, 940, 220], radius=12, fill="#ffffff", outline="#cbd5e1", width=2)
    d.text((762, 52), "Legend", font=font(FONT_BOLD, 20), fill="#334155")
    legend = [("#1d4ed8", "Water"), ("#15803d", "Farmland"), ("#475569", "Road"), ("#64748b", "Building")]
    ly = 92
    for color, label in legend:
        d.text((762, ly), label, font=font(FONT_BOLD, 18), fill=color)
        ly += 32
    # 标题
    d.text((30, 26), "Remote Sensing Demo", font=font(FONT_BOLD, 30), fill="#0f172a")
    d.text((30, 68), "Synthetic image · no real data", font=font(FONT_REG, 18), fill="#64748b")
    out = EXAMPLES / "demo_input.png"
    img.save(out)
    return str(out)


# ============ 1. 真实工具输出演示（before / after） ============
def make_demo_annotated():
    demo_input = make_demo_input()

    # 真实调用：cv_locate 颜色定位（水体蓝 / 农田绿）
    locate_boxes = []
    for color, tag in (("#38bdf8", "Water"), ("#4ade80", "Farmland")):
        r = server.call_cv_locate(
            {"file_path": demo_input, "mode": "color", "color": color, "tolerance": 28}
        )
        boxes = [
            (int(a), int(b), int(c), int(e), tag)
            for a, b, c, e in re.findall(r"像素框 \[(\d+),(\d+),(\d+),(\d+)\]", r["content"][0]["text"])
        ]
        locate_boxes.extend(boxes)

    # 真实调用：文字识别，优先 PaddleOCR，失败回退 Windows OCR
    ocr_engine = "PaddleOCR"
    ocr_lines = []
    ocr_boxes = []
    try:
        lines, err = server._try_paddle_ocr(demo_input, "zh")
    except Exception as e:  # noqa: BLE001
        lines, err = None, str(e)
    if err is not None:
        ocr_engine = "Windows OCR（兜底）"
        wr = server._call_windows_ocr(demo_input, "zh-Hans-CN")
        body = wr["content"][0]["text"].split("文本块位置：")[0]
        if body.startswith("[安全提示]"):
            body = body.split("\n\n", 1)[1] if "\n\n" in body else body
        ocr_lines = [ln for ln in body.splitlines()[1:] if ln.strip()]
    else:
        ocr_boxes = [(l["x"], l["y"], l["w"], l["h"], l["text"]) for l in lines]
        ocr_lines = [t for *_, t in ocr_boxes]
    print("OCR engine:", ocr_engine, "| lines:", len(ocr_lines))
    for ln in ocr_lines[:8]:
        print("  -", ln)

    src = Image.open(demo_input).convert("RGB")
    W, H = src.size
    panel_w = 430
    head_h = 96
    canvas = Image.new("RGB", (W + panel_w + 46, H + head_h), (15, 23, 42))
    d = ImageDraw.Draw(canvas)

    # 顶部标题条
    d.text((30, 22), "本地识图 MCP · 真实工具输出", font=font(FONT_BOLD, 30), fill="#ffffff")
    d.text((30, 64), "颜色定位 + 文字识别（合成示例图，无真实数据）", font=font(FONT_REG, 18), fill="#94a3b8")

    # 左侧：原图 + 标注框
    off_y = head_h
    canvas.paste(src, (30, off_y))
    draw = ImageDraw.Draw(canvas)
    for x1, y1, x2, y2, tag in locate_boxes:
        draw.rectangle([30 + x1, off_y + y1, 30 + x2, off_y + y2], outline="#00e5ff", width=3)
        draw.text((30 + x1, off_y + y1 - 22), tag, font=font(FONT_BOLD, 16), fill="#00e5ff")
    for x, y, w, h, text in ocr_boxes:
        draw.rectangle([30 + x, off_y + y, 30 + x + w, off_y + y + h], outline="#4ade80", width=2)

    # 右侧：结果面板
    px = W + 30 + 30
    d.text((px, off_y + 8), "① 颜色定位 cv_locate", font=font(FONT_BOLD, 20), fill="#00e5ff")
    y = off_y + 42
    for i, (a, b, c, e, tag) in enumerate(locate_boxes, 1):
        d.text((px, y), f"{tag}  [{a},{b},{c},{e}]", font=font(FONT_REG, 16), fill="#cbd5e1")
        y += 26
    y += 10
    d.text((px, y), f"② 文字识别 · {ocr_engine}", font=font(FONT_BOLD, 20), fill="#4ade80")
    y += 34
    for ln in ocr_lines[:14]:
        for wl in wrap_text(d, ln, font(FONT_REG, 16), panel_w - 28):
            if y > H + off_y - 46:
                break
            d.text((px, y), wl, font=font(FONT_REG, 16), fill="#e2e8f0")
            y += 24
        if y > H + off_y - 46:
            break
    d.text((px, H + off_y - 24), "图片全程在本机处理 · 未上传任何云端", font=font(FONT_REG, 14), fill="#64748b")

    out = EXAMPLES / "demo_annotated.png"
    canvas.save(out)
    print("saved", out, canvas.size, "| OCR engine:", ocr_engine)


# ============ 2. GitHub 社交横幅 1200x630 ============
def make_social_preview():
    BW, BH = 1200, 630
    img = Image.new("RGB", (BW, BH), (15, 23, 42))
    d = ImageDraw.Draw(img)
    for y in range(BH):
        t = y / BH
        d.line([(0, y), (BW, y)], fill=(int(15 + 25 * t), int(23 + 34 * t), int(42 + 55 * t)))
    eye_cx, eye_cy, eye_r = 1000, 150, 78
    d.ellipse([eye_cx - eye_r, eye_cy - eye_r, eye_cx + eye_r, eye_cy + eye_r], fill="#2d4a8f")
    d.ellipse([eye_cx - 34, eye_cy - 22, eye_cx + 34, eye_cy + 22], outline="#ffffff", width=7)
    d.ellipse([eye_cx - 12, eye_cy - 12, eye_cx + 12, eye_cy + 12], fill="#ffffff")
    for dx, dy, r in [(180, 90, 4), (240, 180, 3), (150, 300, 5), (700, 520, 4), (830, 560, 3)]:
        d.ellipse([dx - r, dy - r, dx + r, dy + r], fill="#3b82f6")

    d.text((70, 64), "LOCAL VISION MCP · 本地识图", font=font(FONT_BOLD, 30), fill="#38bdf8")
    d.text((70, 120), "给 DeepSeek 装上", font=font(FONT_BOLD, 84), fill="#ffffff")
    d.text((70, 232), "本地眼睛", font=font(FONT_BOLD, 84), fill="#ffffff")
    d.text((70, 344), "OCR · 检测 · 分割 · 零样本 · 定位 · 裁切放大", font=font(FONT_REG, 38), fill="#cbd5e1")
    d.text((70, 400), "图片全程不出本机，100% 本地免费", font=font(FONT_REG, 38), fill="#7dd3fc")
    chips = ["11 个工具", "21 项离线测试", "相同图片缓存秒回", "多轮闭环防幻觉"]
    cx, cy = 70, 492
    for chip in chips:
        tw = d.textlength(chip, font=font(FONT_BOLD, 26))
        d.rounded_rectangle([cx, cy, cx + tw + 36, cy + 54], radius=27, fill="#1e3a5f", outline="#3b82f6", width=2)
        d.text((cx + 18, cy + 10), chip, font=font(FONT_BOLD, 26), fill="#e2e8f0")
        cx += tw + 56
    d.text((70, 574), "github.com/Yuhang-uestc/deepvision-local-mcp", font=font(FONT_REG, 24), fill="#94a3b8")
    out = EXAMPLES / "social_preview.png"
    img.save(out)
    print("saved", out, img.size)


# ============ 3. 架构流程图 ============
def make_architecture():
    AW, AH = 1160, 660
    bg = Image.new("RGB", (AW, AH), (15, 23, 42))
    d = ImageDraw.Draw(bg)
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
    out = EXAMPLES / "architecture.png"
    bg.save(out)
    print("saved", out, bg.size)


if __name__ == "__main__":
    make_demo_annotated()
    make_social_preview()
    make_architecture()
