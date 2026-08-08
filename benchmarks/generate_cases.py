#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成确定性合成基准用例（含标准答案）。

用法：
    python benchmarks/generate_cases.py

输出：
    benchmarks/generated/                     合成图片
    benchmarks/generated/ground_truth.json    标准答案 + 用例清单

设计目标：
- 固定随机种子，同一台机器上每次生成结果一致，保证可复现；
- 不依赖网络、不依赖真实照片；
- 中文用例依赖系统存在 CJK 字体，找不到时自动跳过并在 JSON 里说明原因。
"""

import json
import os
import random
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    sys.exit("需要 Pillow：python -m pip install Pillow")


HERE = Path(__file__).resolve().parent
GEN_DIR = HERE / "generated"
SEED = 20260808

# 与 server.py 的 _NAMED_COLORS 保持一致
NAMED_COLORS = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange": (255, 165, 0),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
}

CJK_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
EN_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def find_font(size, candidates):
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def cjk_font_available():
    return any(os.path.isfile(p) for p in CJK_FONT_CANDIDATES)


def draw_text_block(draw, lines, font, fill, w, h, line_gap=14):
    """把多行文字居中画到画布上。"""
    boxes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
    heights = [b[3] - b[1] for b in boxes]
    total = sum(heights) + line_gap * (len(lines) - 1)
    y = max(0, (h - total) // 2)
    for ln, bb, hh in zip(lines, boxes, heights):
        tw = bb[2] - bb[0]
        x = max(0, (w - tw) // 2 - bb[0])
        draw.text((x, y - bb[1]), ln, font=font, fill=fill)
        y += hh + line_gap


def save(img, name):
    path = GEN_DIR / name
    img.save(path)
    return path


def rects_overlap(a, b, gap=0):
    return not (
        a[2] + gap < b[0]
        or b[2] + gap < a[0]
        or a[3] + gap < b[1]
        or b[3] + gap < a[1]
    )


def place_shapes(rng, count, w, h, half, gap=18):
    """在画布内放置互不重叠的圆形/方形中心点。"""
    placed = []
    attempts = 0
    while len(placed) < count and attempts < 20000:
        attempts += 1
        cx = rng.randint(half + 12, w - half - 12)
        cy = rng.randint(half + 12, h - half - 12)
        box = (cx - half, cy - half, cx + half, cy + half)
        if all(not rects_overlap(box, (px - half, py - half, px + half, py + half), gap) for px, py in placed):
            placed.append((cx, cy))
    if len(placed) < count:
        raise RuntimeError(f"放置 {count} 个图形失败（画布 {w}x{h}）")
    return placed


def gen_ocr_cases(rng, gt, skipped):
    cases = []
    cjk_ok = cjk_font_available()

    specs = [
        # id, text_lines, size, bg, fg, lang
        (
            "ocr_en_01",
            ["The quick brown fox jumps over the lazy dog."],
            32,
            (255, 255, 255),
            (20, 20, 20),
            "en-US",
        ),
        (
            "ocr_en_02",
            ["Order 2026-0812  Total $128.50"],
            28,
            (255, 255, 255),
            (20, 20, 20),
            "en-US",
        ),
        (
            "ocr_cn_01",
            ["本地识图 MCP 测试：中文与英文混合识别"],
            32,
            (255, 255, 255),
            (20, 20, 20),
            "zh-Hans-CN",
        ),
        (
            "ocr_cn_02",
            ["订单号 20260808 已发货 请及时查收"],
            28,
            (255, 255, 255),
            (20, 20, 20),
            "zh-Hans-CN",
        ),
        (
            "ocr_table_01",
            ["项目    数量    金额", "笔记本   2      899.00", "显示器   1      1299.50"],
            26,
            (255, 255, 255),
            (20, 20, 20),
            "zh-Hans-CN",
        ),
        (
            "ocr_small_01",
            ["conf 0.80 iou 0.50 epoch 120"],
            16,
            (255, 255, 255),
            (30, 30, 30),
            "en-US",
        ),
        (
            "ocr_white_on_dark",
            ["Status: All systems normal"],
            30,
            (0, 40, 90),
            (255, 255, 255),
            "en-US",
        ),
        (
            "ocr_digits_01",
            ["0123456789 9876543210 555-1234"],
            30,
            (255, 255, 255),
            (20, 20, 20),
            "en-US",
        ),
        (
            "ocr_punct_01",
            ["Error: file not found! (code 404)"],
            26,
            (255, 255, 255),
            (20, 20, 20),
            "en-US",
        ),
        (
            "ocr_para_01",
            [
                "Local Vision MCP provides OCR, detection",
                "and segmentation for pure-text LLMs like",
                "DeepSeek. All processing stays on-device.",
            ],
            24,
            (255, 255, 255),
            (20, 20, 20),
            "en-US",
        ),
        (
            "ocr_low_contrast",
            ["Low contrast test 123"],
            26,
            (255, 255, 255),
            (125, 125, 125),
            "en-US",
        ),
        (
            "ocr_colored_text",
            ["Status OK 456"],
            28,
            (250, 245, 210),
            (0, 110, 60),
            "en-US",
        ),
        (
            "ocr_cn_para",
            ["视觉识别的准确率取决于图像质量", "本工具支持中文与英文混排"],
            26,
            (255, 255, 255),
            (20, 20, 20),
            "zh-Hans-CN",
        ),
        (
            "ocr_mixed_cn_en",
            ["版本 v2.2.0 更新于 2026-08-08"],
            26,
            (255, 255, 255),
            (20, 20, 20),
            "zh-Hans-CN",
        ),
        (
            "ocr_small_cn",
            ["小字中文测试 2026"],
            16,
            (255, 255, 255),
            (30, 30, 30),
            "zh-Hans-CN",
        ),
    ]

    for cid, lines, size, bg, fg, lang in specs:
        need_cjk = any("\u4e00" <= ch <= "\u9fff" for ln in lines for ch in ln)
        if need_cjk and not cjk_ok:
            skipped.append({"id": cid, "reason": "本机没有可用的 CJK 字体，跳过中文用例"})
            continue
        font = find_font(size, CJK_FONT_CANDIDATES if need_cjk else EN_FONT_CANDIDATES)
        w, h = 820, 120 + 44 * len(lines)
        img = Image.new("RGB", (w, h), bg)
        draw = ImageDraw.Draw(img)
        draw_text_block(draw, [ln.strip() for ln in lines], font, fg, w, h)
        save(img, f"{cid}.png")
        cases.append(
            {
                "id": cid,
                "file": f"generated/{cid}.png",
                "expected_text": "\n".join(ln.strip() for ln in lines),
                "language": lang,
            }
        )
    return cases


def gen_color_cases(rng, gt):
    cases = []

    def add(name, color_name, boxes, file_name=None, tolerance=40):
        cases.append(
            {
                "id": name,
                "file": f"generated/{file_name or name}.png",
                "color": color_name,
                "tolerance": tolerance,
                "min_area": 50,
                "merge": True,
                "expected_boxes": boxes,
            }
        )

    # 1) 白底 5 个红色圆
    w, h, half = 640, 480, 32
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    centers = place_shapes(rng, 5, w, h, half)
    boxes = []
    for cx, cy in centers:
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["red"])
        boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_red_dots.png")
    add("color_red_dots", "red", boxes)

    # 2) 白底 3 个蓝色方块
    w, h, half = 640, 480, 28
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    centers = place_shapes(rng, 3, w, h, half)
    boxes = []
    for cx, cy in centers:
        draw.rectangle((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["blue"])
        boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_blue_squares.png")
    add("color_blue_squares", "blue", boxes)

    # 3) 多色混合：红 x2 / 绿 x2 / 蓝 x1，同一张图按颜色分别建用例
    w, h, half = 720, 480, 30
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    per_color = {"red": 2, "green": 2, "blue": 1}
    boxes_of = {c: [] for c in per_color}
    for color_name, count in per_color.items():
        centers = place_shapes(rng, count, w, h, half)
        for cx, cy in centers:
            draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS[color_name])
            boxes_of[color_name].append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_multi.png")
    for color_name in per_color:
        add(f"color_multi_{color_name}", color_name, boxes_of[color_name], file_name="color_multi")

    # 4) 近色干扰：2 红 + 2 粉 + 1 橙，红色容差 40 应只命中 2 个
    w, h, half = 720, 480, 30
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    red_boxes = []
    pink_centers = place_shapes(rng, 2, w, h, half)
    orange_centers = place_shapes(rng, 1, w, h, half)
    red_centers = place_shapes(rng, 2, w, h, half)
    for cx, cy in pink_centers:
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=(255, 150, 150))
    for cx, cy in orange_centers:
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["orange"])
    for cx, cy in red_centers:
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["red"])
        red_boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_near_distractors.png")
    add("color_near_distractors", "red", red_boxes)

    # 5) 计数管线：10 个绿色小圆点（验证"数 N 个"能力）
    w, h, half = 700, 500, 20
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    centers = place_shapes(rng, 10, w, h, half, gap=14)
    boxes = []
    for cx, cy in centers:
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["green"])
        boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_count_10.png")
    add("color_count_10", "green", boxes)

    # 6) 黄色方块 x4
    w, h, half = 640, 480, 26
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    centers = place_shapes(rng, 4, w, h, half)
    boxes = []
    for cx, cy in centers:
        draw.rectangle((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["yellow"])
        boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_yellow_squares.png")
    add("color_yellow_squares", "yellow", boxes)

    # 7) 青色圆 x3
    w, h, half = 640, 480, 30
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    centers = place_shapes(rng, 3, w, h, half)
    boxes = []
    for cx, cy in centers:
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["cyan"])
        boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_cyan_dots.png")
    add("color_cyan_dots", "cyan", boxes)

    # 8) 小红点 x8（小目标计数）
    w, h, half = 700, 500, 12
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    centers = place_shapes(rng, 8, w, h, half, gap=14)
    boxes = []
    for cx, cy in centers:
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["red"])
        boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_tiny_red_dots.png")
    add("color_tiny_red_dots", "red", boxes)

    # 9) 同色混合形状：2 圆 + 2 方（验证按颜色计数与形状无关）
    w, h, half = 720, 480, 28
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    centers = place_shapes(rng, 4, w, h, half)
    boxes = []
    for i, (cx, cy) in enumerate(centers):
        if i % 2 == 0:
            draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["red"])
        else:
            draw.rectangle((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["red"])
        boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_mixed_shapes_red.png")
    add("color_mixed_shapes_red", "red", boxes)

    # 10) 低容差：3 个红色圆，tolerance 10 应仍能全部命中（颜色精确）
    w, h, half = 640, 480, 30
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    centers = place_shapes(rng, 3, w, h, half)
    boxes = []
    for cx, cy in centers:
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=NAMED_COLORS["red"])
        boxes.append([cx - half, cy - half, cx + half, cy + half])
    save(img, "color_tolerance_low.png")
    add("color_tolerance_low", "red", boxes, tolerance=10)

    return cases


def gen_template_cases(rng):
    cases = []
    # 徽章模板：蓝底 + 白边 + 橙圆 + 数字，非纯色，可被模板匹配
    tpl_size = 64
    tpl = Image.new("RGB", (tpl_size, tpl_size), (30, 90, 200))
    td = ImageDraw.Draw(tpl)
    td.rounded_rectangle((2, 2, tpl_size - 3, tpl_size - 3), radius=14, outline=(255, 255, 255), width=4)
    td.ellipse((18, 18, 46, 46), fill=(255, 165, 0))
    tpl_path = GEN_DIR / "tpl_badge.png"
    tpl.save(tpl_path)

    def make_scene(name, bg, pos, rects):
        w, h = 600, 400
        img = Image.new("RGB", (w, h), bg)
        draw = ImageDraw.Draw(img)
        for r in rects:
            draw.rectangle(r, fill=(220, 220, 225))
        x, y = pos
        img.paste(tpl, (x, y))
        save(img, f"{name}.png")
        return [x, y, x + tpl_size, y + tpl_size]

    rects_a = []
    for _ in range(6):
        x1 = rng.randint(0, 480)
        y1 = rng.randint(0, 300)
        rects_a.append((x1, y1, x1 + rng.randint(40, 100), y1 + rng.randint(20, 60)))
    rects_b = []
    for _ in range(6):
        x1 = rng.randint(0, 480)
        y1 = rng.randint(0, 300)
        rects_b.append((x1, y1, x1 + rng.randint(30, 80), y1 + rng.randint(30, 90)))

    box_a = make_scene("tpl_badge_scene_a", (238, 238, 238), (140, 110), rects_a)
    box_b = make_scene("tpl_badge_scene_b", (250, 246, 240), (320, 70), rects_b)
    # 双实例场景：同一徽章出现两次，验证多实例匹配
    w, h = 600, 400
    img = Image.new("RGB", (w, h), (232, 238, 244))
    draw = ImageDraw.Draw(img)
    for _ in range(6):
        x1 = rng.randint(0, 480)
        y1 = rng.randint(0, 300)
        draw.rectangle((x1, y1, x1 + rng.randint(40, 90), y1 + rng.randint(20, 70)), fill=(214, 222, 230))
    pos1, pos2 = (80, 60), (380, 240)
    img.paste(tpl, pos1)
    img.paste(tpl, pos2)
    save(img, "tpl_badge_scene_c.png")
    box_c = [
        [pos1[0], pos1[1], pos1[0] + tpl_size, pos1[1] + tpl_size],
        [pos2[0], pos2[1], pos2[0] + tpl_size, pos2[1] + tpl_size],
    ]

    for cid, fname, boxes in [
        ("tpl_badge_a", "tpl_badge_scene_a.png", [box_a]),
        ("tpl_badge_b", "tpl_badge_scene_b.png", [box_b]),
        ("tpl_badge_multi", "tpl_badge_scene_c.png", box_c),
    ]:
        cases.append(
            {
                "id": cid,
                "file": f"generated/{fname}",
                "template": "generated/tpl_badge.png",
                "threshold": 0.75,
                "method": "TM_CCOEFF_NORMED",
                "expected_boxes": boxes,
            }
        )
    return cases


def gen_image_info_cases():
    # 多格式：同一张底图存成 jpg / bmp / tiff，验证格式识别
    base = Image.new("RGB", (320, 240), (255, 255, 255))
    bd = ImageDraw.Draw(base)
    bd.rectangle((20, 20, 160, 140), fill=(230, 60, 60))
    bd.ellipse((180, 100, 300, 220), fill=(40, 90, 220))
    base.save(GEN_DIR / "fmt_base.png")
    base.save(GEN_DIR / "fmt_base.jpg")
    base.save(GEN_DIR / "fmt_base.bmp")
    base.save(GEN_DIR / "fmt_base.tiff")
    return [
        {
            "id": "info_en_01",
            "file": "generated/ocr_en_01.png",
            "expected": {"w": 820, "h": 164, "format": "PNG", "mode": "RGB"},
        },
        {
            "id": "info_color_red_dots",
            "file": "generated/color_red_dots.png",
            "expected": {"w": 640, "h": 480, "format": "PNG", "mode": "RGB"},
        },
        {
            "id": "info_jpeg",
            "file": "generated/fmt_base.jpg",
            "expected": {"w": 320, "h": 240, "format": "JPEG", "mode": "RGB"},
        },
        {
            "id": "info_bmp",
            "file": "generated/fmt_base.bmp",
            "expected": {"w": 320, "h": 240, "format": "BMP", "mode": "RGB"},
        },
        {
            "id": "info_tiff",
            "file": "generated/fmt_base.tiff",
            "expected": {"w": 320, "h": 240, "format": "TIFF", "mode": "RGB"},
        },
    ]


def gen_crop_cases(rng):
    cases = []
    w, h = 800, 600
    img = Image.new("RGB", (w, h), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    # 上半红条
    draw.rectangle((0, 0, w, 120), fill=(230, 60, 60))
    # 左绿块
    draw.rectangle((0, 120, 200, 600), fill=(60, 180, 90))
    # 蓝色圆
    draw.ellipse((350, 200, 520, 370), fill=(40, 90, 220))
    # 黄色方块
    draw.rectangle((560, 400, 700, 540), fill=(240, 210, 40))
    # 一些灰色细节
    for _ in range(12):
        x = rng.randint(20, w - 120)
        y = rng.randint(20, h - 60)
        draw.rectangle((x, y, x + rng.randint(30, 90), y + rng.randint(10, 40)), fill=(180, 180, 185))
    save(img, "crop_scene.png")

    box = [100, 100, 500, 400]
    cases.append(
        {
            "id": "crop_exact",
            "file": "generated/crop_scene.png",
            "box": box,
            "scale": 1,
            "output_size": [400, 300],
        }
    )
    cases.append(
        {
            "id": "crop_scale2",
            "file": "generated/crop_scene.png",
            "box": box,
            "scale": 2,
            "output_size": [800, 600],
        }
    )
    # 归一化坐标：0.125/0.25/0.5/0.625 精确对应 [100,150,400,375]
    cases.append(
        {
            "id": "crop_normalized",
            "file": "generated/crop_scene.png",
            "box": [0.125, 0.25, 0.5, 0.625],
            "normalized": True,
            "scale": 1,
            "output_size": [300, 225],
        }
    )
    # 外扩边距：box [100,100,300,200] margin 10 -> [90,90,310,210]
    cases.append(
        {
            "id": "crop_margin",
            "file": "generated/crop_scene.png",
            "box": [100, 100, 300, 200],
            "margin": 10,
            "scale": 1,
            "output_size": [220, 120],
        }
    )
    return cases


def gen_validation_cases():
    fake = GEN_DIR / "fake_not_a_png.png"
    fake.write_bytes(b"this is definitely not a real png file")
    zero = GEN_DIR / "v_zero_byte.png"
    zero.write_bytes(b"")
    mismatch = GEN_DIR / "v_ext_mismatch.jpg"
    Image.new("RGB", (32, 32), (255, 0, 0)).save(mismatch, format="PNG")
    return [
        {"id": "v_missing_file", "file": "generated/does_not_exist.png", "expect": "error", "pass_raw": False},
        {"id": "v_not_image", "file": "generated/fake_not_a_png.png", "expect": "error", "pass_raw": False},
        {"id": "v_relative_path", "file": "generated/ocr_en_01.png", "expect": "error", "pass_raw": True},
        {"id": "v_zero_byte", "file": "generated/v_zero_byte.png", "expect": "error", "pass_raw": False},
        {"id": "v_directory", "file": "generated", "expect": "error", "pass_raw": False},
        {
            "id": "v_ext_mismatch",
            "file": "generated/v_ext_mismatch.jpg",
            "expect": "accept",
            "pass_raw": False,
            "expect_note": "扩展名",
            "note": "PNG 内容 + .jpg 扩展名：按内容校验应被接受，且 image_info 提示扩展名与实际格式不符",
        },
    ]


def gen_draw_cases():
    return [
        {
            "id": "draw_single_box",
            "file": "generated/crop_scene.png",
            "boxes": [{"x1": 40, "y1": 40, "x2": 300, "y2": 220, "color": "red"}],
            "line_width": 4,
        },
        {
            "id": "draw_two_boxes",
            "file": "generated/crop_scene.png",
            "boxes": [
                {"x1": 40, "y1": 40, "x2": 300, "y2": 220, "color": "red"},
                {"x1": 420, "y1": 300, "x2": 700, "y2": 560, "color": "blue"},
            ],
            "line_width": 4,
        },
    ]


def gen_analyze_cases():
    return [
        {
            "id": "analyze_smoke",
            "file": "generated/ocr_en_01.png",
            "prompt": "这张图片里写了什么？请用中文回答。",
            "mode": "quick",
        }
    ]


def main():
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    skipped = []
    gt = {
        "schema_version": 1,
        "seed": SEED,
        "cjk_font_found": cjk_font_available(),
        "skipped": skipped,
        "cases": {},
    }
    gt["cases"]["ocr"] = gen_ocr_cases(rng, gt, skipped)
    gt["cases"]["color"] = gen_color_cases(rng, gt)
    gt["cases"]["template"] = gen_template_cases(rng)
    gt["cases"]["image_info"] = gen_image_info_cases()
    gt["cases"]["crop"] = gen_crop_cases(rng)
    gt["cases"]["draw"] = gen_draw_cases()
    gt["cases"]["validation"] = gen_validation_cases()
    gt["cases"]["analyze"] = gen_analyze_cases()

    out = GEN_DIR / "ground_truth.json"
    out.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in gt["cases"].values())
    print(f"generated {total} cases -> {GEN_DIR}")
    if skipped:
        print(f"skipped {len(skipped)}: {[s['id'] for s in skipped]}")


if __name__ == "__main__":
    main()
