#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Vision MCP Server v2
==========================

给纯文本主模型（DeepSeek 等）补上"看图"能力的本地 MCP server。
图片只在本机处理，不离开机器。

工具总览：
  analyze_image      本地视觉模型看图（Ollama + Qwen3-VL 等），支持多图对比
  ocr_extract        Windows 内置 OCR 逐字提取文字（含位置）
  detect_objects     YOLO 检测 COCO 80 类常见物体
  detect_by_text     YOLOE / YOLO-World 零样本检测：用文字描述找任意物体
  cv_locate          颜色分割 / 模板匹配定位（不依赖深度学习模型）
  crop_image         裁切 + 放大局部区域，用于小字/小目标二次识别
  draw_bounding_box  绘制一个或多个边界框，可视化验证定位结果
  image_info         读取图片基本信息（尺寸、格式、大小）
  list_local_models  列出本机 Ollama 模型

依赖策略：
  - 基础服务：零第三方依赖（Python 标准库）
  - analyze_image / ocr_extract / image_info：无需第三方库
  - crop_image / draw_bounding_box：需要 Pillow
  - cv_locate：需要 numpy + OpenCV（随 ultralytics 安装），有纯 numpy 兜底
  - detect_objects / detect_by_text：需要 ultralytics

环境变量：
  OLLAMA_HOST           Ollama 地址，默认 http://localhost:11434
  OLLAMA_VISION_MODEL   视觉模型名，默认 qwen3-vl:8b
  LOCAL_VISION_MAX_MB   单张图片大小上限(MB)，默认 20
  DETECTION_MODEL       默认 COCO 检测模型，默认 yolov8n.pt
  DETECTION_TEXT_MODEL   默认零样本检测模型，默认 yoloe-v8s-seg.pt
  VISION_OUTPUT_DIR     可选。设置后所有生成文件只能写入该目录
"""

import base64
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

SERVER_NAME = "local-vision"
SERVER_VERSION = "2.0.0"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen3-vl:8b")
MAX_IMAGE_BYTES = int(os.environ.get("LOCAL_VISION_MAX_MB", "20")) * 1024 * 1024

DEFAULT_PROMPT = "请详细描述这张图片的内容，包括画面主体、布局和图中出现的所有文字。"

TOOLS = [
    {
        "name": "analyze_image",
        "description": (
            "用本地视觉模型（Ollama）分析一张或多张本地图片，返回文字描述，用于给纯文本主模型补看图能力。"
            "传 file_path 单张图；需要对比（如原图 vs 放大图）时传 file_paths 数组。图片仅在本机处理。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "本地图片文件的绝对路径，例如 C:/Users/xxx/Desktop/photo.png",
                },
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选。多张图片的绝对路径数组，模型会按顺序看到这些图，可做对比。",
                },
                "prompt": {
                    "type": "string",
                    "description": "可选。对图片的分析要求，默认是详细描述内容。",
                },
                "model": {
                    "type": "string",
                    "description": "可选。覆盖默认视觉模型，例如 qwen3-vl:4b。",
                },
                "temperature": {
                    "type": "number",
                    "description": "可选。采样温度，0-2，越低越保守，默认用模型默认值。",
                },
            },
            "required": [],
        },
    },
    {
        "name": "image_info",
        "description": (
            "读取本地图片的基本信息（尺寸、格式、文件大小），用于确定坐标系和判断是否需要放大。"
            "要求用户描述位置或画框前建议先调用本工具。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本地图片文件的绝对路径"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "list_local_models",
        "description": "列出本机 Ollama 已安装的全部模型，可用于确认视觉模型是否已就绪。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ocr_extract",
        "description": (
            "用系统内置 OCR 从本地图片中逐字提取文字，支持中文/英文，返回文本和每个文本块的位置。"
            "适合截图、文档、含小字的图片。小字建议先裁切放大再调用。图片仅在本机处理。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "本地图片文件的绝对路径，支持 jpg/png/bmp/tiff",
                },
                "language": {
                    "type": "string",
                    "description": "可选。OCR 语言，默认 zh-Hans-CN，可用 en-US",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "detect_objects",
        "description": (
            "用 YOLO 目标检测模型精确定位图片中的常见物体（人物、车辆、动物等 COCO 80 类），"
            "返回每个物体的类别、置信度和像素/归一化边界框坐标。用于数人数、找常见物体、给精确坐标。"
            "可通过 save_path 保存标注图。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本地图片的绝对路径"},
                "min_confidence": {
                    "type": "number",
                    "description": "可选。置信度阈值，默认 0.35",
                },
                "classes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选。只保留指定类别，例如 [\"person\", \"car\"]",
                },
                "model": {
                    "type": "string",
                    "description": "可选。检测模型，默认 yolov8n.pt，可换 yolov8s.pt 等",
                },
                "save_path": {
                    "type": "string",
                    "description": "可选。保存标注图的绝对路径，省略则自动生成",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "detect_by_text",
        "description": (
            "零样本目标检测（YOLOE / YOLO-World）：不需要训练，用文字描述就能找任意物体，"
            "例如 text=\"消防栓, 蓝色帐篷\"。返回每个目标的类别、置信度和坐标框。"
            "默认模型 yoloe-v8s-seg.pt，首次使用需联网下载（约 30MB）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本地图片的绝对路径"},
                "text": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要检测的物体描述，可多个，例如 [\"person\", \"red car\"]；也接受逗号分隔字符串",
                },
                "min_confidence": {
                    "type": "number",
                    "description": "可选。置信度阈值，默认 0.3",
                },
                "model": {
                    "type": "string",
                    "description": "可选。零样本模型，默认 yoloe-v8s-seg.pt，也可用 yolov8s-world.pt",
                },
                "save_path": {
                    "type": "string",
                    "description": "可选。保存标注图的绝对路径，省略则自动生成",
                },
            },
            "required": ["file_path", "text"],
        },
    },
    {
        "name": "cv_locate",
        "description": (
            "不用深度学习模型做定位：mode=color 按颜色找区域（如图例色块、指定颜色的物体），"
            "mode=template 用小图做模板匹配找图标/logo。返回坐标框，坐标可直接用于 crop_image 或 draw_bounding_box。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本地图片的绝对路径"},
                "mode": {
                    "type": "string",
                    "description": "color（默认）或 template",
                },
                "color": {
                    "type": "string",
                    "description": "color 模式：目标颜色，如 \"#ff0000\"、\"red\" 或 [255,0,0]",
                },
                "tolerance": {
                    "type": "number",
                    "description": "color 模式：颜色容差 0-255，默认 40",
                },
                "min_area": {
                    "type": "number",
                    "description": "color 模式：最小区域面积（像素），默认 50，用于过滤噪点",
                },
                "merge": {
                    "type": "boolean",
                    "description": "color 模式：是否合并相邻区域，默认 true",
                },
                "template_path": {
                    "type": "string",
                    "description": "template 模式：模板小图的绝对路径",
                },
                "threshold": {
                    "type": "number",
                    "description": "template 模式：匹配阈值，默认 0.75（TM_CCOEFF_NORMED 越接近 1 越像）",
                },
                "method": {
                    "type": "string",
                    "description": "template 模式：TM_CCOEFF_NORMED（默认）/ TM_CCORR_NORMED / TM_SQDIFF_NORMED",
                },
                "scales": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "template 模式：缩放搜索尺度，默认 [1.0]；小目标可试 [0.5, 1.0, 1.5, 2.0]",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "crop_image",
        "description": (
            "裁切图片局部区域并按比例放大保存为新文件。小字、小目标、印章、仪表读数必须先裁切放大再识别，"
            "这是提高识别精度的关键步骤。可配合 scale=2~4 放大，再对放大图调用 OCR 或视觉模型。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "输入图片的绝对路径"},
                "output_path": {
                    "type": "string",
                    "description": "可选。输出图片的绝对路径，省略则自动生成到 outputs 目录",
                },
                "x1": {"type": "number", "description": "区域左上角 X（像素）"},
                "y1": {"type": "number", "description": "区域左上角 Y（像素）"},
                "x2": {"type": "number", "description": "区域右下角 X（像素）"},
                "y2": {"type": "number", "description": "区域右下角 Y（像素）"},
                "normalized": {
                    "type": "boolean",
                    "description": "可选。坐标是否为 0-1 归一化值，默认 false",
                },
                "margin": {
                    "type": "number",
                    "description": "可选。在裁切区域外扩的边距（像素），默认 0",
                },
                "scale": {
                    "type": "number",
                    "description": "可选。放大倍数，默认 1；小字建议 2-4",
                },
            },
            "required": ["file_path", "x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "draw_bounding_box",
        "description": (
            "在图片上绘制一个或多个边界框（可带标签、可指定颜色），保存为新文件。"
            "一次传 boxes 数组即可同时框出多个目标，用于定位可视化验证。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "输入图片的绝对路径"},
                "output_path": {
                    "type": "string",
                    "description": "可选。输出图片的绝对路径，省略则自动生成到 outputs 目录",
                },
                "boxes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "x1": {"type": "number", "description": "框左上角 X"},
                            "y1": {"type": "number", "description": "框左上角 Y"},
                            "x2": {"type": "number", "description": "框右下角 X"},
                            "y2": {"type": "number", "description": "框右下角 Y"},
                            "label": {"type": "string", "description": "可选。框上的标签文字"},
                            "confidence": {"type": "number", "description": "可选。置信度，会拼在标签后"},
                            "color": {
                                "type": "string",
                                "description": "可选。颜色，如 \"#00ff00\"、\"red\"，默认红",
                            },
                            "normalized": {
                                "type": "boolean",
                                "description": "可选。该框坐标是否为 0-1 归一化，默认 false",
                            },
                        },
                        "required": ["x1", "y1", "x2", "y2"],
                    },
                    "description": "多个边界框的数组；不传时使用下方单框参数",
                },
                "x1": {"type": "number", "description": "单框模式：框左上角 X"},
                "y1": {"type": "number", "description": "单框模式：框左上角 Y"},
                "x2": {"type": "number", "description": "单框模式：框右下角 X"},
                "y2": {"type": "number", "description": "单框模式：框右下角 Y"},
                "label": {"type": "string", "description": "单框模式：框上的标签文字"},
                "confidence": {"type": "number", "description": "单框模式：置信度"},
                "color": {"type": "string", "description": "单框模式：颜色，默认红"},
                "normalized": {
                    "type": "boolean",
                    "description": "单框模式：坐标是否为 0-1 归一化，默认 false",
                },
                "line_width": {"type": "number", "description": "可选。框线宽度，默认 4"},
            },
            "required": ["image_path"],
        },
    },
]


def log(msg: str) -> None:
    """日志走 stderr，避免污染 stdout 上的 MCP 协议消息。"""
    try:
        print(f"[local-vision] {msg}", file=sys.stderr, flush=True)
    except Exception:
        pass


def ollama_generate(model: str, prompt: str, images_b64: list, options: dict = None, timeout: int = 900) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "images": images_b64,
        "stream": False,
    }
    if options:
        payload["options"] = options
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data.get("response") or ""
    if not text:
        text = (data.get("message") or {}).get("content", "")
    return text


def read_image_b64(file_path: str) -> str:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"找不到图片文件：{file_path}")
    size = os.path.getsize(file_path)
    if size > MAX_IMAGE_BYTES:
        raise ValueError(
            f"图片过大（{size / 1024 / 1024:.1f}MB > {MAX_IMAGE_BYTES / 1024 / 1024:.0f}MB），请换一张较小的图"
        )
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _require_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont

        return Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError("缺少 Pillow，请先安装：python -m pip install Pillow")


_FONT_CACHE = {}


def _load_font(size: int = 16):
    """优先加载支持中文的 Windows 字体，避免中文标签画成方块。"""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    from PIL import ImageFont

    for p in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
    ):
        if os.path.isfile(p):
            try:
                font = ImageFont.truetype(p, size)
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue
    font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


_NAMED_COLORS = {
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


def _parse_color(value, default=(255, 0, 0)):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError, IndexError):
            return default
    s = str(value).strip()
    if s.lower() in _NAMED_COLORS:
        return _NAMED_COLORS[s.lower()]
    s = s.lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return default


def _parse_rect(args: dict, w: int, h: int, normalized_default: bool = False):
    try:
        x1 = float(args.get("x1"))
        y1 = float(args.get("y1"))
        x2 = float(args.get("x2"))
        y2 = float(args.get("y2"))
    except (TypeError, ValueError):
        raise ValueError("x1/y1/x2/y2 必须是数字")
    normalized = bool(args.get("normalized", normalized_default))
    if normalized:
        x1, x2 = x1 * w, x2 * w
        y1, y2 = y1 * h, y2 * h
    box = [int(round(v)) for v in (x1, y1, x2, y2)]
    box = [
        max(0, min(box[0], w - 1)),
        max(0, min(box[1], h - 1)),
        max(0, min(box[2], w - 1)),
        max(0, min(box[3], h - 1)),
    ]
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("区域无效：x2 必须大于 x1 且 y2 必须大于 y1")
    return box


def _auto_output_path(input_path: str, suffix: str) -> str:
    root = os.environ.get("VISION_OUTPUT_DIR", "").strip()
    if not root:
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
    os.makedirs(root, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(root, f"{stem}_{suffix}.png")


def _safe_output_path(input_path: str, output_path: str) -> str:
    out = os.path.abspath(output_path)
    root = os.environ.get("VISION_OUTPUT_DIR", "").strip()
    if root:
        root_abs = os.path.abspath(root)
        try:
            inside = os.path.commonpath([root_abs, out]) == root_abs
        except ValueError:
            inside = False
        if not inside:
            raise ValueError(f"VISION_OUTPUT_DIR 已启用，输出文件必须位于 {root_abs} 内")
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if input_path and os.path.abspath(input_path).lower() == out.lower():
        raise ValueError("输出路径不能覆盖输入图片")
    return out


def _rects_intersect(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) > 0 and max(0, min(a[3], b[3]) - max(a[1], b[1])) > 0


def _merge_rects(rects):
    rects = [tuple(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        used = [False] * len(rects)
        for i, a in enumerate(rects):
            if used[i]:
                continue
            x1, y1, x2, y2 = a
            for j in range(i + 1, len(rects)):
                b = rects[j]
                if used[j]:
                    continue
                if _rects_intersect(a, b):
                    x1 = min(x1, b[0])
                    y1 = min(y1, b[1])
                    x2 = max(x2, b[2])
                    y2 = max(y2, b[3])
                    used[j] = True
                    changed = True
            out.append((x1, y1, x2, y2))
        rects = out
    return rects


def _nms_matches(matches, overlap=0.4, reverse=True):
    matches = sorted(matches, key=lambda m: m[0], reverse=reverse)
    keep = []
    for m in matches:
        bx1, by1 = m[1], m[2]
        bx2, by2 = m[1] + m[3], m[2] + m[4]
        dup = False
        for k in keep:
            kx1, ky1 = k[1], k[2]
            kx2, ky2 = k[1] + k[3], k[2] + k[4]
            inter = max(0, min(bx2, kx2) - max(bx1, kx1)) * max(0, min(by2, ky2) - max(by1, ky1))
            area_b = (bx2 - bx1) * (by2 - by1)
            area_k = (kx2 - kx1) * (ky2 - ky1)
            union = area_b + area_k - inter
            if union > 0 and inter / union > overlap:
                dup = True
                break
        if not dup:
            keep.append(m)
    return keep


def call_analyze_image(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    file_paths = args.get("file_paths")
    paths = []
    if isinstance(file_paths, (list, tuple)):
        paths = [str(p).strip() for p in file_paths if str(p).strip()]
    if file_path:
        paths = [file_path] + [p for p in paths if p != file_path]
    if not paths:
        return err_result("缺少 file_path：请提供本地图片的绝对路径（或传 file_paths 数组做多图对比）")
    prompt = str(args.get("prompt", "")).strip() or DEFAULT_PROMPT
    model = str(args.get("model", "")).strip() or VISION_MODEL
    options = {}
    temperature = args.get("temperature")
    if temperature is not None:
        try:
            options["temperature"] = float(temperature)
        except (TypeError, ValueError):
            return err_result("temperature 必须是数字")

    try:
        images = [read_image_b64(p) for p in paths]
        log(f"正在用 {model} 分析 {len(paths)} 张图 ...")
        text = ollama_generate(model, prompt, images, options=options)
        return ok_result(text)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if e.code == 404:
            return err_result(f"Ollama 返回 404：模型 {model!r} 不存在。请先运行：ollama pull {model}")
        return err_result(f"Ollama 请求失败（HTTP {e.code}）：{body or e}")
    except urllib.error.URLError as e:
        return err_result(f"无法连接 Ollama（{OLLAMA_HOST}）：{e.reason}。请确认 Ollama 已启动（ollama serve）。")
    except Exception as e:
        return err_result(f"分析失败：{e}")


def call_image_info(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    if not file_path:
        return err_result("缺少 file_path 参数：请提供本地图片的绝对路径")
    if not os.path.isfile(file_path):
        return err_result(f"找不到图片文件：{file_path}")
    try:
        Image = _require_pillow()[0]
    except ImportError as e:
        return err_result(str(e))
    try:
        size_bytes = os.path.getsize(file_path)
        with Image.open(file_path) as im:
            w, h = im.size
            fmt = im.format or "未知"
            mode = im.mode
        return ok_result(
            f"图片信息：\n路径：{file_path}\n尺寸：{w} x {h}\n格式：{fmt}\n模式：{mode}\n"
            f"大小：{size_bytes / 1024:.1f} KB\n（坐标使用像素，x∈[0,{w - 1}], y∈[0,{h - 1}]）"
        )
    except Exception as e:
        return err_result(f"读取图片信息失败：{e}")


def call_list_models() -> dict:
    try:
        req = urllib.request.Request(OLLAMA_HOST + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = sorted(m.get("name", "") for m in data.get("models", []))
        if not names:
            return ok_result("本机 Ollama 还没有安装任何模型。先运行：ollama pull qwen3-vl:8b")
        lines = [f"{name}  <-- 当前视觉模型" if name == VISION_MODEL else name for name in names]
        return ok_result("本机 Ollama 模型：\n" + "\n".join(lines))
    except Exception as e:
        return err_result(f"获取模型列表失败：{e}")


def call_ocr_extract(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    if not file_path:
        return err_result("缺少 file_path 参数：请提供本地图片的绝对路径")
    if not os.path.isfile(file_path):
        return err_result(f"找不到图片文件：{file_path}")
    lang = str(args.get("language", "")).strip() or "zh-Hans-CN"

    server_dir = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(server_dir, "win_ocr.ps1")
    cache_dir = os.path.join(server_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)

    ext = os.path.splitext(file_path)[1] or ".jpg"
    img_key = hashlib.md5(file_path.encode("utf-8")).hexdigest()
    cached_img = os.path.join(cache_dir, img_key + ext)
    tmp_key = hashlib.md5((file_path + os.urandom(8).hex()).encode("utf-8")).hexdigest()
    tmp_name = os.path.join(cache_dir, tmp_key + ".json")
    shell = shutil.which("pwsh") or "powershell"

    try:
        shutil.copy2(file_path, cached_img)
        proc = subprocess.run(
            [
                shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                "-ImagePath", cached_img, "-OutFile", tmp_name, "-Lang", lang,
            ],
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            return err_result(f"OCR 失败：{stderr or '未知错误'}")
        with open(tmp_name, encoding="utf-8-sig") as f:
            data = json.load(f)
    except subprocess.TimeoutExpired:
        return err_result("OCR 超时")
    except Exception as e:
        return err_result(f"OCR 失败：{e}")
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        try:
            os.unlink(cached_img)
        except OSError:
            pass

    text = str(data.get("text", "")).strip()
    lines = data.get("lines") or []
    if not text:
        return ok_result("图中未识别到文字。")
    blocks = "\n".join(
        f"- [{l.get('x')},{l.get('y')},{l.get('w')}x{l.get('h')}] {l.get('text')}" for l in lines
    )
    return ok_result(f"OCR 识别文字（{data.get('language', lang)}）：\n{text}\n\n文本块位置：\n{blocks}")


def call_crop_image(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    if not file_path:
        return err_result("缺少 file_path 参数")
    if not os.path.isfile(file_path):
        return err_result(f"找不到图片文件：{file_path}")
    try:
        Image = _require_pillow()[0]
    except ImportError as e:
        return err_result(str(e))
    try:
        img = Image.open(file_path)
        w, h = img.size
        try:
            box = _parse_rect(args, w, h)
        except ValueError as e:
            return err_result(str(e))
        margin = int(args.get("margin", 0) or 0)
        if margin > 0:
            box = [
                max(0, box[0] - margin),
                max(0, box[1] - margin),
                min(w - 1, box[2] + margin),
                min(h - 1, box[3] + margin),
            ]
        try:
            scale = float(args.get("scale", 1) or 1)
        except (TypeError, ValueError):
            return err_result("scale 必须是数字")
        if scale <= 0:
            return err_result("scale 必须大于 0")
        region = img.crop(box)
        if abs(scale - 1.0) > 1e-6:
            nw = max(1, int(round((box[2] - box[0]) * scale)))
            nh = max(1, int(round((box[3] - box[1]) * scale)))
            resample = getattr(Image, "Resampling", Image).LANCZOS
            region = region.resize((nw, nh), resample)
        output_path = str(args.get("output_path", "")).strip()
        if not output_path:
            output_path = _auto_output_path(file_path, "crop")
        output_path = _safe_output_path(file_path, output_path)
        region.save(output_path)
        return ok_result(
            f"已裁切并保存到 {output_path}。\n原图 {w}x{h}，裁切区域像素框 {box}，"
            f"缩放 {scale}x，输出 {region.size[0]}x{region.size[1]}。"
        )
    except Exception as e:
        return err_result(f"裁切失败：{e}")


def call_draw_box(args: dict) -> dict:
    image_path = str(args.get("image_path", "")).strip()
    if not image_path:
        return err_result("缺少 image_path 参数")
    if not os.path.isfile(image_path):
        return err_result(f"找不到图片文件：{image_path}")
    try:
        Image, ImageDraw, ImageFont = _require_pillow()
    except ImportError as e:
        return err_result(str(e))

    try:
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        draw = ImageDraw.Draw(img)
        boxes = args.get("boxes")
        if boxes is None:
            boxes = [args]
        if not isinstance(boxes, list) or not boxes:
            return err_result("缺少 boxes 数组（或 x1/y1/x2/y2 单框参数）")
        try:
            line_width = int(args.get("line_width", 4) or 4)
        except (TypeError, ValueError):
            line_width = 4
        font = _load_font(16)
        drawn = []
        for item in boxes:
            if not isinstance(item, dict):
                return err_result("boxes 中每一项必须是对象")
            try:
                box = _parse_rect(item, w, h)
            except ValueError as e:
                return err_result(str(e))
            color = _parse_color(item.get("color"))
            label = str(item.get("label", "")).strip()
            conf = item.get("confidence")
            if label and conf is not None:
                try:
                    label = f"{label} {float(conf):.2f}"
                except (TypeError, ValueError):
                    pass
            draw.rectangle(box, outline=color, width=line_width)
            if label:
                ty = max(0, box[1] - 22)
                try:
                    draw.text((box[0], ty), label, fill=color, font=font)
                except Exception:
                    draw.text((box[0], ty), label, fill=color)
            drawn.append({"box": box, "label": label or "无标签"})
        output_path = str(args.get("output_path", "")).strip()
        if not output_path:
            output_path = _auto_output_path(image_path, "boxes")
        output_path = _safe_output_path(image_path, output_path)
        img.save(output_path)
        summary = "\n".join(f"- {d['label']}: {d['box']}" for d in drawn)
        return ok_result(f"已绘制 {len(drawn)} 个边界框并保存到 {output_path}。图片尺寸 {w}x{h}。\n{summary}")
    except Exception as e:
        return err_result(f"绘制失败：{e}")


def _cv_locate_color(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    color = _parse_color(args.get("color"))
    try:
        tolerance = float(args.get("tolerance", 40) or 40)
    except (TypeError, ValueError):
        return err_result("tolerance 必须是数字")
    tolerance = max(0.0, min(255.0, tolerance))
    try:
        min_area = float(args.get("min_area", 50) or 50)
    except (TypeError, ValueError):
        return err_result("min_area 必须是数字")
    merge = bool(args.get("merge", True))

    try:
        import cv2
        import numpy as np
    except ImportError:
        return err_result("颜色定位需要 numpy + opencv-python（随 ultralytics 一起安装）：python -m pip install opencv-python")

    try:
        img = cv2.imread(file_path)
        if img is None:
            return err_result(f"无法读取图片：{file_path}")
        h, w = img.shape[:2]
        b, g, r = int(color[2]), int(color[1]), int(color[0])
        lower = np.array([max(0, b - tolerance), max(0, g - tolerance), max(0, r - tolerance)], dtype=np.uint8)
        upper = np.array([min(255, b + tolerance), min(255, g + tolerance), min(255, r + tolerance)], dtype=np.uint8)
        mask = cv2.inRange(img, lower, upper)
        if merge:
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rects = []
        for c in contours:
            area = cv2.contourArea(c)
            if area >= min_area:
                x, y, cw, ch = cv2.boundingRect(c)
                rects.append((x, y, x + cw, y + ch))
        if merge:
            rects = _merge_rects(rects)
        if not rects:
            return ok_result(f"未找到颜色 {color}（容差 {tolerance}）的区域。")
        lines = []
        for i, (x1, y1, x2, y2) in enumerate(rects, 1):
            area = (x2 - x1) * (y2 - y1)
            lines.append(
                f"- 区域{i}：像素框 [{x1},{y1},{x2},{y2}]，"
                f"归一化 [{x1 / w:.3f},{y1 / h:.3f},{x2 / w:.3f},{y2 / h:.3f}]，面积 {area}px"
            )
        hex_color = "#{:02x}{:02x}{:02x}".format(*color)
        return ok_result(f"颜色定位（{hex_color}，容差 {tolerance}）：找到 {len(rects)} 个区域（图片 {w}x{h}）：\n" + "\n".join(lines))
    except Exception as e:
        return err_result(f"颜色定位失败：{e}")


def _cv_locate_template(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    template_path = str(args.get("template_path", "")).strip()
    if not template_path:
        return err_result("template 模式需要 template_path 参数")
    if not os.path.isfile(template_path):
        return err_result(f"找不到模板文件：{template_path}")
    try:
        threshold = float(args.get("threshold", 0.75) or 0.75)
    except (TypeError, ValueError):
        return err_result("threshold 必须是数字")
    method_name = str(args.get("method", "TM_CCOEFF_NORMED")).strip()
    if method_name not in ("TM_CCOEFF_NORMED", "TM_CCORR_NORMED", "TM_SQDIFF_NORMED"):
        return err_result("method 只能是 TM_CCOEFF_NORMED / TM_CCORR_NORMED / TM_SQDIFF_NORMED")
    scales = args.get("scales")
    if isinstance(scales, str):
        scales = [float(s.strip()) for s in scales.split(",") if s.strip()]
    if not isinstance(scales, (list, tuple)) or not scales:
        scales = [1.0]

    try:
        import cv2
        import numpy as np
    except ImportError:
        return err_result("模板匹配需要 numpy + opencv-python（随 ultralytics 一起安装）：python -m pip install opencv-python")

    try:
        img = cv2.imread(file_path)
        tpl0 = cv2.imread(template_path)
        if img is None:
            return err_result(f"无法读取图片：{file_path}")
        if tpl0 is None:
            return err_result(f"无法读取模板：{template_path}")
        img_h, img_w = img.shape[:2]
        th, tw = tpl0.shape[:2]
        if th > img_h or tw > img_w:
            return err_result("模板尺寸大于原图，无法匹配")
        if int(tpl0.min()) == int(tpl0.max()):
            return err_result("模板是纯色图，无法匹配（归一化相关性对常数模板退化）。请裁取包含纹理/边缘的区域作为模板。")
        flag = getattr(cv2, method_name)
        invert = method_name == "TM_SQDIFF_NORMED"
        candidates = []
        for scale in scales:
            try:
                scale = float(scale)
            except (TypeError, ValueError):
                continue
            if scale <= 0:
                continue
            tpl = tpl0
            if abs(scale - 1.0) > 1e-6:
                tpl = cv2.resize(tpl0, (max(1, int(round(tw * scale))), max(1, int(round(th * scale)))))
            if tpl.shape[0] > img_h or tpl.shape[1] > img_w:
                continue
            res = cv2.matchTemplate(img, tpl, flag)
            if invert:
                loc = np.where(res <= threshold)
            else:
                loc = np.where(res >= threshold)
            for y_idx, x_idx in zip(*loc):
                candidates.append(
                    (float(res[y_idx, x_idx]), int(x_idx), int(y_idx), tpl.shape[1], tpl.shape[0], scale)
                )
        if not candidates:
            return ok_result(
                f"模板匹配未找到高于阈值 {threshold} 的位置（方法 {method_name}，尺度 {scales}）。"
            )
        keep = _nms_matches(candidates, overlap=0.4, reverse=not invert)[:10]
        lines = []
        for i, (score, x, y, cw, ch, scale) in enumerate(keep, 1):
            x2, y2 = x + cw, y + ch
            lines.append(
                f"- 匹配{i}：得分 {score:.3f}，尺度 {scale:.2f}x，像素框 [{x},{y},{x2},{y2}]，"
                f"归一化 [{x / img_w:.3f},{y / img_h:.3f},{x2 / img_w:.3f},{y2 / img_h:.3f}]"
            )
        return ok_result(f"模板匹配（{method_name}，阈值 {threshold}）：找到 {len(keep)} 处（图片 {img_w}x{img_h}）：\n" + "\n".join(lines))
    except Exception as e:
        return err_result(f"模板匹配失败：{e}")


def call_cv_locate(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    if not file_path:
        return err_result("缺少 file_path 参数")
    if not os.path.isfile(file_path):
        return err_result(f"找不到图片文件：{file_path}")
    mode = str(args.get("mode", "color")).strip().lower()
    if mode in ("color", "colour"):
        return _cv_locate_color(args)
    if mode == "template":
        return _cv_locate_template(args)
    return err_result("mode 只能是 color 或 template")


_DETECTION_MODEL_CACHE = {}


def _get_detection_model(model_name: str = None):
    server_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_dir = os.path.join(server_dir, ".cache", "ultralytics")
    os.makedirs(cfg_dir, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", cfg_dir)
    from ultralytics import YOLO

    name = model_name or os.environ.get("DETECTION_MODEL", "yolov8n.pt")
    if not os.path.isabs(name) and os.path.sep not in name and "/" not in name:
        local_model = os.path.join(server_dir, name)
        if os.path.isfile(local_model):
            name = local_model
    if name not in _DETECTION_MODEL_CACHE:
        _DETECTION_MODEL_CACHE[name] = YOLO(name)
    return _DETECTION_MODEL_CACHE[name]


def _resolve_classes(model, classes):
    resolved = []
    names = {str(v).lower(): int(k) for k, v in (model.names or {}).items()}
    for c in classes:
        key = str(c).strip().lower()
        if key in names:
            resolved.append(names[key])
        else:
            try:
                resolved.append(int(c))
            except (TypeError, ValueError):
                raise ValueError(f"类别 '{c}' 不在模型类别中（可用：{sorted((model.names or {}).values())}）")
    return resolved or None


def _format_detection_results(results):
    r = results[0]
    img_h, img_w = r.orig_shape
    if r.boxes is None or len(r.boxes) == 0:
        return None, f"未检测到任何目标（图片 {img_w}x{img_h}）。"
    lines = []
    for box in r.boxes:
        x1, y1, x2, y2 = [round(float(v), 1) for v in box.xyxy[0].tolist()]
        conf_v = round(float(box.conf[0]), 3)
        cls_id = int(box.cls[0])
        name = (r.names or {}).get(cls_id, str(cls_id))
        lines.append(
            f"- {name} ({conf_v})：像素框 [{x1},{y1},{x2},{y2}]，"
            f"归一化 [{x1 / img_w:.3f},{y1 / img_h:.3f},{x2 / img_w:.3f},{y2 / img_h:.3f}]"
        )
    return r, f"检测到 {len(lines)} 个目标（图片 {img_w}x{img_h}）：\n" + "\n".join(lines)


def _save_plot(results, save_path: str):
    from PIL import Image

    arr = results[0].plot()
    Image.fromarray(arr[..., ::-1]).save(save_path)


def call_detect_objects(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    if not file_path:
        return err_result("缺少 file_path 参数：请提供本地图片的绝对路径")
    if not os.path.isfile(file_path):
        return err_result(f"找不到图片文件：{file_path}")
    try:
        conf = float(args.get("min_confidence", 0.35))
    except (TypeError, ValueError):
        return err_result("min_confidence 必须是数字")
    classes = args.get("classes")
    if isinstance(classes, str):
        classes = [c.strip() for c in classes.split(",") if c.strip()]
    model_name = str(args.get("model", "")).strip() or os.environ.get("DETECTION_MODEL", "yolov8n.pt")
    stem = os.path.splitext(os.path.basename(model_name))[0]
    if "yoloe" in stem or "world" in stem:
        return err_result("这是零样本检测模型，请使用 detect_by_text 工具并传入 text 描述")

    try:
        with contextlib.redirect_stdout(sys.stderr):
            model = _get_detection_model(model_name)
    except ImportError:
        return err_result("未安装目标检测依赖，请先运行：python -m pip install ultralytics")
    except Exception as e:
        return err_result(f"加载检测模型失败：{e}。首次使用需要联网下载权重（{model_name}）。")

    try:
        if classes:
            try:
                classes = _resolve_classes(model, classes)
            except ValueError as e:
                return err_result(str(e))
        with contextlib.redirect_stdout(sys.stderr):
            results = model.predict(file_path, conf=conf, classes=classes, verbose=False)
        r, msg = _format_detection_results(results)
        save_path = str(args.get("save_path", "")).strip()
        if save_path:
            try:
                out = _safe_output_path(file_path, save_path)
                with contextlib.redirect_stdout(sys.stderr):
                    _save_plot(results, out)
                msg += f"\n标注图已保存：{out}"
            except Exception as e:
                msg += f"\n（保存标注图失败：{e}）"
        return ok_result(msg)
    except Exception as e:
        return err_result(f"检测失败：{e}")


def call_detect_by_text(args: dict) -> dict:
    file_path = str(args.get("file_path", "")).strip()
    if not file_path:
        return err_result("缺少 file_path 参数：请提供本地图片的绝对路径")
    if not os.path.isfile(file_path):
        return err_result(f"找不到图片文件：{file_path}")
    text = args.get("text")
    if not text:
        return err_result("缺少 text 参数：请描述要检测的物体，如 \"person\" 或 [\"person\", \"red car\"]")
    if isinstance(text, str):
        texts = [t.strip() for t in text.split(",") if t.strip()]
    elif isinstance(text, (list, tuple)):
        texts = [str(t).strip() for t in text if str(t).strip()]
    else:
        texts = []
    texts = list(dict.fromkeys(texts))
    if not texts:
        return err_result("text 解析后为空")
    try:
        conf = float(args.get("min_confidence", 0.3))
    except (TypeError, ValueError):
        return err_result("min_confidence 必须是数字")
    model_name = str(args.get("model", "")).strip() or os.environ.get("DETECTION_TEXT_MODEL", "yoloe-v8s-seg.pt")
    stem = os.path.splitext(os.path.basename(model_name))[0]
    if "yoloe" not in stem and "world" not in stem:
        return err_result(
            f"模型 {model_name} 不是零样本模型；请用 detect_objects，或选择 yoloe / yolo-world 模型"
        )

    try:
        with contextlib.redirect_stdout(sys.stderr):
            model = _get_detection_model(model_name)
    except ImportError:
        return err_result("未安装目标检测依赖，请先运行：python -m pip install ultralytics")
    except Exception as e:
        return err_result(f"加载检测模型失败：{e}。首次使用需要联网下载权重（{model_name}）。")

    try:
        with contextlib.redirect_stdout(sys.stderr):
            model.set_classes(texts)
            results = model.predict(file_path, conf=conf, verbose=False)
        r, msg = _format_detection_results(results)
        save_path = str(args.get("save_path", "")).strip()
        if save_path:
            try:
                out = _safe_output_path(file_path, save_path)
                with contextlib.redirect_stdout(sys.stderr):
                    _save_plot(results, out)
                msg += f"\n标注图已保存：{out}"
            except Exception as e:
                msg += f"\n（保存标注图失败：{e}）"
        return ok_result(msg)
    except Exception as e:
        return err_result(f"检测失败：{e}")


def ok_result(text: str) -> dict:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": False,
    }


def err_result(message: str) -> dict:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def handle_tools_call(msg: dict) -> dict:
    params = msg.get("params") or {}
    name = params.get("name", "")
    args = params.get("arguments") or {}
    result = {"jsonrpc": "2.0", "id": msg.get("id")}
    if name == "analyze_image":
        result["result"] = call_analyze_image(args)
    elif name == "image_info":
        result["result"] = call_image_info(args)
    elif name == "list_local_models":
        result["result"] = call_list_models()
    elif name == "ocr_extract":
        result["result"] = call_ocr_extract(args)
    elif name == "crop_image":
        result["result"] = call_crop_image(args)
    elif name == "draw_bounding_box":
        result["result"] = call_draw_box(args)
    elif name == "cv_locate":
        result["result"] = call_cv_locate(args)
    elif name == "detect_objects":
        result["result"] = call_detect_objects(args)
    elif name == "detect_by_text":
        result["result"] = call_detect_by_text(args)
    else:
        result["error"] = {"code": -32602, "message": f"未知工具：{name}"}
    return result


def handle(msg: dict):
    method = msg.get("method")

    if method == "initialize":
        params = msg.get("params") or {}
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "result": {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {"tools": TOOLS}}

    if method == "tools/call":
        return handle_tools_call(msg)

    if "id" in msg:
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    log(f"启动 v{SERVER_VERSION}，视觉模型={VISION_MODEL}，Ollama={OLLAMA_HOST}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            resp = handle(msg)
        except Exception as e:
            log(f"处理消息出错：{e}")
            if "id" in msg:
                resp = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(e)}}
            else:
                resp = None
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
