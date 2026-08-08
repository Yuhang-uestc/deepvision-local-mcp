#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行基准测试：对照标准答案调用本地工具并计算指标。

用法：
    python benchmarks/run_benchmark.py
    python benchmarks/run_benchmark.py --engines windows
    python benchmarks/run_benchmark.py --dataset benchmarks/datasets/my_photos.json
    python benchmarks/run_benchmark.py --strict

常用参数：
    --engines     OCR 引擎，逗号分隔，可选 auto/windows/paddle，默认 auto
    --dataset     额外标准答案（用于自己标注的检测数据集）
    --only        只跑部分类型，如 ocr,color
    --out         报告输出目录，默认 benchmarks/report
    --strict      有失败用例时退出码为 1（供 CI 使用）
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


BOX_RE = re.compile(r"像素框 \[\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\]")
OCR_BODY_RE = re.compile(r"OCR 识别文字（.*?）：\n(.*?)(?:\n\n文本块位置：|\Z)", re.S)
INFO_RE = re.compile(r"尺寸：(\d+) x (\d+)\n格式：(\w+)\n模式：(\w+)")
CROP_SAVE_RE = re.compile(r"已裁切并保存到 (.+?)。")
CROP_SIZE_RE = re.compile(r"输出 (\d+)x(\d+)")
DET_COUNT_RE = re.compile(r"检测到 (\d+) 个目标")
DRAW_SAVE_RE = re.compile(r"已绘制 (\d+) 个边界框并保存到 (.+?)。")

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


def result_text(res):
    if not isinstance(res, dict):
        return "", True, "工具返回格式异常"
    content = res.get("content") or []
    text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
    if text.startswith(server.UNTRUSTED_PREFIX):
        text = text[len(server.UNTRUSTED_PREFIX):]
    return text, bool(res.get("isError")), None


def levenshtein(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[lb]


def parse_ocr_lines(text):
    if "未识别到文字" in text:
        return []
    m = OCR_BODY_RE.search(text)
    if not m:
        return None
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]


def norm_ocr_line(s, has_cjk):
    """OCR 文本归一化：全角转半角；中文去掉所有空白，英文折叠为单个空格。"""
    s = unicodedata.normalize("NFKC", s)
    if has_cjk:
        return re.sub(r"\s+", "", s)
    return " ".join(s.split())


def has_cjk(s):
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def norm_blob(s):
    """全角转半角并去掉全部空白，用于跨行内容比对（容忍换行/分栏差异）。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def parse_boxes(text):
    return [[int(g) for g in m] for m in BOX_RE.findall(text)]


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def eval_boxes(gt_boxes, pred_boxes, iou_thr=0.5):
    matched = 0
    used = set()
    overlaps = []
    for gb in gt_boxes:
        best_i, best_v = -1, 0.0
        for j, pb in enumerate(pred_boxes):
            if j in used:
                continue
            v = iou(gb, pb)
            if v > best_v:
                best_v, best_i = v, j
        if best_i >= 0 and best_v >= iou_thr:
            matched += 1
            used.add(best_i)
        overlaps.append(best_v)
    recall = matched / len(gt_boxes) if gt_boxes else 1.0
    precision = matched / len(pred_boxes) if pred_boxes else (1.0 if not gt_boxes else 0.0)
    return {
        "count_gt": len(gt_boxes),
        "count_pred": len(pred_boxes),
        "matched": matched,
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "mean_iou": round(sum(overlaps) / len(overlaps) if overlaps else 0.0, 4),
    }


def call_tool(fn, args):
    t0 = time.time()
    try:
        res = fn(args)
        err = None
    except Exception as e:  # noqa: BLE001
        res, err = None, f"{type(e).__name__}: {e}"
    return res, err, time.time() - t0


def resolve(path_str):
    p = Path(path_str)
    if not p.is_absolute():
        p = HERE / p
    return str(p.resolve())


def run_ocr(case, engine, report_dir):
    res, err, elapsed = call_tool(
        server.call_ocr_extract,
        {
            "file_path": resolve(case["file"]),
            "engine": engine,
            "language": case.get("language", "zh-Hans-CN"),
        },
    )
    if err:
        return fail_result(case, engine, f"工具异常：{err}", elapsed, "ocr")
    text, is_err, _ = result_text(res)
    if is_err:
        return fail_result(case, engine, f"OCR 报错：{text[:300]}", elapsed, "ocr")
    lines = parse_ocr_lines(text)
    if lines is None:
        return fail_result(case, engine, f"输出格式解析失败，原文：{text[:200]}", elapsed, "ocr")
    cjk = has_cjk(case["expected_text"])
    gt_lines = [norm_ocr_line(ln, cjk) for ln in case["expected_text"].splitlines() if ln.strip()]
    pred_lines = [norm_ocr_line(ln, cjk) for ln in lines]
    gt_norm = "".join(gt_lines)
    pred_norm = "".join(pred_lines)
    cer = levenshtein(gt_norm, pred_norm) / max(1, max(len(gt_norm), len(pred_norm)))
    # 内容覆盖率：每行标准文字是否完整出现在识别结果中（容忍 OCR 换行/分栏差异）
    gt_units = [norm_blob(ln) for ln in case["expected_text"].splitlines() if ln.strip()]
    pred_blob = norm_blob("".join(lines))
    content_recall = sum(1 for u in gt_units if u and u in pred_blob) / len(gt_units) if gt_units else 1.0
    ok = cer <= 0.20 and content_recall >= 0.8
    return {
        "id": case["id"],
        "kind": "ocr",
        "engine": engine,
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": {
            "cer": round(cer, 4),
            "content_recall": round(content_recall, 4),
            "gt_chars": len(gt_norm),
            "pred_chars": len(pred_norm),
        },
        "detail": f"预测：{' / '.join(pred_lines[:5]) or '(空)'}",
    }


def run_color(case, report_dir):
    res, err, elapsed = call_tool(
        server.call_cv_locate,
        {
            "file_path": resolve(case["file"]),
            "mode": "color",
            "color": case["color"],
            "tolerance": case.get("tolerance", 40),
            "min_area": case.get("min_area", 50),
            "merge": case.get("merge", True),
        },
    )
    if err:
        return fail_result(case, None, f"工具异常：{err}", elapsed, "color")
    text, is_err, _ = result_text(res)
    if is_err:
        return fail_result(case, None, f"颜色定位报错：{text[:300]}", elapsed, "color")
    pred = parse_boxes(text)
    m = eval_boxes(case["expected_boxes"], pred)
    ok = m["count_pred"] == m["count_gt"] and m["recall"] >= 0.8
    return {
        "id": case["id"],
        "kind": "color",
        "engine": None,
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": m,
        "detail": f"颜色 {case['color']}，期望 {m['count_gt']} 个，检出 {m['count_pred']} 个",
    }


def run_template(case, report_dir):
    res, err, elapsed = call_tool(
        server.call_cv_locate,
        {
            "file_path": resolve(case["file"]),
            "mode": "template",
            "template_path": resolve(case["template"]),
            "threshold": case.get("threshold", 0.75),
            "method": case.get("method", "TM_CCOEFF_NORMED"),
        },
    )
    if err:
        return fail_result(case, None, f"工具异常：{err}", elapsed, "template")
    text, is_err, _ = result_text(res)
    if is_err:
        return fail_result(case, None, f"模板匹配报错：{text[:300]}", elapsed, "template")
    pred = parse_boxes(text)
    if not pred:
        return fail_result(case, None, "未找到任何匹配位置", elapsed, "template")
    expected = case.get("expected_boxes") or ([case["expected_box"]] if case.get("expected_box") else [])
    m = eval_boxes(expected, pred)
    ok = m["recall"] >= 0.8 and m["count_pred"] >= 1
    return {
        "id": case["id"],
        "kind": "template",
        "engine": None,
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": m,
        "detail": f"期望 {m['count_gt']} 处，检出 {m['count_pred']} 处，召回 {m['recall']:.2f}",
    }


def run_image_info(case, report_dir):
    res, err, elapsed = call_tool(server.call_image_info, {"file_path": resolve(case["file"])})
    if err:
        return fail_result(case, None, f"工具异常：{err}", elapsed, "image_info")
    text, is_err, _ = result_text(res)
    if is_err:
        return fail_result(case, None, f"图片信息报错：{text[:300]}", elapsed, "image_info")
    m = INFO_RE.search(text)
    if not m:
        return fail_result(case, None, f"输出格式解析失败，原文：{text[:200]}", elapsed, "image_info")
    got = {"w": int(m.group(1)), "h": int(m.group(2)), "format": m.group(3), "mode": m.group(4)}
    exp = case["expected"]
    ok = got == exp
    return {
        "id": case["id"],
        "kind": "image_info",
        "engine": None,
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": got,
        "detail": f"期望 {exp}，实际 {got}",
    }


def run_crop(case, report_dir):
    from PIL import Image

    out_dir = report_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{case['id']}.png"
    src = Image.open(resolve(case["file"]))
    w, h = src.size
    box = case["box"]
    normalized = bool(case.get("normalized"))
    if normalized:
        box = [int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)]
    margin = int(case.get("margin", 0) or 0)
    final_box = box
    if margin:
        final_box = [
            max(0, box[0] - margin),
            max(0, box[1] - margin),
            min(w - 1, box[2] + margin),
            min(h - 1, box[3] + margin),
        ]
    call_args = {
        "file_path": resolve(case["file"]),
        "x1": case["box"][0],
        "y1": case["box"][1],
        "x2": case["box"][2],
        "y2": case["box"][3],
        "scale": case.get("scale", 1),
        "output_path": str(out_path),
    }
    if normalized:
        call_args["normalized"] = True
    if margin:
        call_args["margin"] = margin
    res, err, elapsed = call_tool(
        server.call_crop_image,
        call_args,
    )
    if err:
        return fail_result(case, None, f"工具异常：{err}", elapsed, "crop")
    text, is_err, _ = result_text(res)
    if is_err:
        return fail_result(case, None, f"裁切报错：{text[:300]}", elapsed, "crop")
    m = CROP_SIZE_RE.search(text)
    if not m or not out_path.is_file():
        return fail_result(case, None, f"输出格式解析失败：{text[:200]}", elapsed, "crop")
    got_size = [int(m.group(1)), int(m.group(2))]
    ok = got_size == case["output_size"]
    detail = f"输出尺寸 {got_size[0]}x{got_size[1]}"
    if ok:
        region = src.crop(final_box)
        if case.get("scale", 1) != 1:
            region = region.resize(
                (case["output_size"][0], case["output_size"][1]),
                Image.Resampling.LANCZOS,
            )
        with Image.open(out_path) as out_img:
            same = out_img.size == region.size and out_img.tobytes() == region.tobytes()
        ok = same
        detail += f"，像素完全一致：{same}"
    return {
        "id": case["id"],
        "kind": "crop",
        "engine": None,
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": {"output_size": got_size, "pixels_match": ok},
        "detail": detail,
    }


def run_validation(case, report_dir):
    file_arg = case["file"] if case.get("pass_raw") else resolve(case["file"])
    res, err, elapsed = call_tool(server.call_image_info, {"file_path": file_arg})
    if err:
        return fail_result(case, None, f"工具异常：{err}", elapsed, "validation")
    text, is_err, _ = result_text(res)
    expect = case.get("expect", "error")
    if expect == "accept":
        ok = not is_err
        note_shown = case.get("expect_note", "") in text if ok else False
        if case.get("expect_note"):
            ok = ok and note_shown
        if is_err:
            detail = f"被拒绝（预期接受）：{text[:200]}"
        elif note_shown:
            detail = "按内容校验通过，且提示了扩展名不符"
        else:
            detail = f"按内容校验通过但缺少扩展名提示：{text[:200]}"
    else:
        ok = is_err
        note_shown = None
        detail = "非法输入被拒绝" if is_err else "非法输入未被拒绝！"
    return {
        "id": case["id"],
        "kind": "validation",
        "engine": None,
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": {"rejected": is_err, "note_shown": note_shown},
        "detail": detail,
    }


def run_detection(case, report_dir):
    if case.get("tool") == "detect_by_text":
        fn = server.call_detect_by_text
        args = {"file_path": resolve(case["file"]), "text": case.get("text", "")}
        if case.get("model"):
            args["model"] = case["model"]
        if case.get("min_confidence") is not None:
            args["min_confidence"] = case["min_confidence"]
    else:
        fn = server.call_detect_objects
        args = {"file_path": resolve(case["file"])}
        if case.get("model"):
            args["model"] = case["model"]
        if case.get("classes"):
            args["classes"] = case["classes"]
        if case.get("min_confidence") is not None:
            args["min_confidence"] = case["min_confidence"]
    res, err, elapsed = call_tool(fn, args)
    if err:
        return fail_result(case, None, f"工具异常：{err}", elapsed, "detection")
    text, is_err, _ = result_text(res)
    if is_err:
        return fail_result(case, None, f"检测报错：{text[:300]}", elapsed, "detection")
    m = DET_COUNT_RE.search(text)
    if not m:
        return fail_result(case, None, f"输出格式解析失败：{text[:200]}", elapsed, "detection")
    got = int(m.group(1))
    exp = case.get("expected_count")
    ok = got == exp
    return {
        "id": case["id"],
        "kind": "detection",
        "engine": case.get("model", ""),
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": {"count_expected": exp, "count_pred": got},
        "detail": f"期望 {exp} 个，检出 {got} 个",
    }


def run_drawbox(case, report_dir):
    from PIL import Image

    out_dir = report_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{case['id']}.png"
    res, err, elapsed = call_tool(
        server.call_draw_box,
        {
            "image_path": resolve(case["file"]),
            "boxes": case["boxes"],
            "line_width": case.get("line_width", 4),
            "output_path": str(out_path),
        },
    )
    if err:
        return fail_result(case, None, f"工具异常：{err}", elapsed, "draw")
    text, is_err, _ = result_text(res)
    if is_err:
        return fail_result(case, None, f"绘制报错：{text[:300]}", elapsed, "draw")
    m = DRAW_SAVE_RE.search(text)
    if not m or not out_path.is_file():
        return fail_result(case, None, f"输出格式解析失败：{text[:200]}", elapsed, "draw")
    drawn_count = int(m.group(1))
    expected_count = len(case["boxes"])
    with Image.open(out_path) as img:
        probes_ok = 0
        probes_total = 0
        for b in case["boxes"]:
            color = NAMED_COLORS.get(b.get("color", "red"), (255, 0, 0))
            x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
            pts = [
                (x1, (y1 + y2) // 2),
                (x2, (y1 + y2) // 2),
                ((x1 + x2) // 2, y1),
                ((x1 + x2) // 2, y2),
            ]
            for pt in pts:
                probes_total += 1
                if img.getpixel(pt) == color:
                    probes_ok += 1
    ok = drawn_count == expected_count and probes_ok == probes_total
    return {
        "id": case["id"],
        "kind": "draw",
        "engine": None,
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": {"boxes_expected": expected_count, "boxes_drawn": drawn_count, "probes_ok": probes_ok, "probes_total": probes_total},
        "detail": f"期望 {expected_count} 个框，绘制 {drawn_count} 个，描边像素命中 {probes_ok}/{probes_total}",
    }


def run_analyze(case, report_dir):
    res, err, elapsed = call_tool(
        server.call_analyze_image,
        {
            "file_path": resolve(case["file"]),
            "prompt": case.get("prompt", ""),
            "mode": case.get("mode", "quick"),
        },
    )
    if err:
        return fail_result(case, None, f"工具异常：{err}", elapsed, "analyze")
    text, is_err, _ = result_text(res)
    if is_err:
        if "无法连接 Ollama" in text:
            return {
                "id": case["id"],
                "kind": "analyze",
                "engine": None,
                "status": "skip",
                "elapsed": round(elapsed, 2),
                "metrics": {},
                "detail": "Ollama 未启动，跳过（环境问题，非工具缺陷）",
            }
        if "404" in text and "模型" in text:
            return {
                "id": case["id"],
                "kind": "analyze",
                "engine": None,
                "status": "skip",
                "elapsed": round(elapsed, 2),
                "metrics": {},
                "detail": f"视觉模型未安装，跳过：{text[:120]}",
            }
        return fail_result(case, None, f"分析报错：{text[:300]}", elapsed, "analyze")
    body = text.strip()
    ok = len(body) >= 5
    return {
        "id": case["id"],
        "kind": "analyze",
        "engine": None,
        "status": "pass" if ok else "fail",
        "elapsed": round(elapsed, 2),
        "metrics": {"chars": len(body)},
        "detail": f"返回内容（前 120 字）：{body[:120]}",
    }


def fail_result(case, engine, detail, elapsed, kind):
    return {
        "id": case["id"],
        "kind": kind,
        "engine": engine,
        "status": "fail",
        "elapsed": round(elapsed, 2),
        "metrics": {},
        "detail": detail,
    }


RUNNERS = {
    "ocr": run_ocr,
    "color": run_color,
    "template": run_template,
    "image_info": run_image_info,
    "crop": run_crop,
    "draw": run_drawbox,
    "validation": run_validation,
    "detection": run_detection,
    "analyze": run_analyze,
}


def run_all(gt, engines, only, report_dir, with_ollama):
    results = []
    total = 0
    for kind, cases in gt.get("cases", {}).items():
        if only and kind not in only:
            continue
        if kind == "analyze" and not with_ollama:
            continue
        for case in cases:
            total += len(engines) if kind == "ocr" else 1
    print(f"共 {total} 个用例")
    n = 0
    for kind, cases in gt.get("cases", {}).items():
        if only and kind not in only:
            continue
        if kind == "analyze" and not with_ollama:
            continue
        for case in cases:
            if kind == "ocr":
                for engine in engines:
                    n += 1
                    r = run_ocr(case, engine, report_dir)
                    results.append(r)
                    print(f"[{n}/{total}] {r['id']} [{engine}] {r['status'].upper()} ({r['elapsed']}s)")
            else:
                n += 1
                r = RUNNERS[kind](case, report_dir)
                results.append(r)
                print(f"[{n}/{total}] {r['id']} {r['status'].upper()} ({r['elapsed']}s)")
    return results


def summarize(results):
    by_kind = {}
    for r in results:
        by_kind.setdefault(r["kind"], []).append(r)
    summary = {}
    for kind, rs in by_kind.items():
        passed = sum(1 for r in rs if r["status"] == "pass")
        failed = sum(1 for r in rs if r["status"] == "fail")
        skipped = sum(1 for r in rs if r["status"] == "skip")
        item = {
            "total": len(rs),
            "pass": passed,
            "fail": failed,
            "skip": skipped,
            "avg_elapsed": round(sum(r["elapsed"] for r in rs) / len(rs), 2),
            "max_elapsed": round(max(r["elapsed"] for r in rs), 2),
        }
        if kind == "ocr":
            valid = [r for r in rs if r["metrics"].get("cer") is not None]
            item["avg_cer"] = round(sum(r["metrics"].get("cer", 1.0) for r in valid) / len(valid), 4) if valid else None
            item["avg_content_recall"] = round(
                sum(r["metrics"].get("content_recall", 0.0) for r in valid) / len(valid), 4
            ) if valid else None
        if kind in ("color", "detection"):
            counts = [r["metrics"]["count_pred"] == r["metrics"]["count_gt"] for r in rs if r["metrics"].get("count_pred") is not None]
            item["count_accuracy"] = round(sum(counts) / len(counts), 4) if counts else None
        if kind in ("color", "template"):
            if kind == "color":
                valid = [r for r in rs if r["metrics"].get("recall") is not None]
                item["avg_recall"] = round(sum(r["metrics"]["recall"] for r in valid) / len(valid), 4) if valid else None
            else:
                valid = [r for r in rs if r["metrics"].get("mean_iou") is not None]
                item["avg_iou"] = round(sum(r["metrics"]["mean_iou"] for r in valid) / len(valid), 4) if valid else None
        if kind == "draw":
            valid = [r for r in rs if r["metrics"].get("probes_total")]
            item["probe_hit_rate"] = round(
                sum(r["metrics"]["probes_ok"] for r in valid) / sum(r["metrics"]["probes_total"] for r in valid), 4
            ) if valid else None
        summary[kind] = item
    return summary


def write_md(results, summary, engines, report_dir):
    lines = [
        "# 本地视觉 MCP 基准测试报告",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- OCR 引擎：{'、'.join(engines)}",
        "",
        "## 总览",
        "",
        "| 类型 | 用例数 | 通过 | 失败 | 跳过 | 平均耗时(s) | 最慢(s) | 关键指标 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for kind, s in summary.items():
        def fmt(v):
            return "-" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v)
        extra = {
            "ocr": f"平均CER {fmt(s.get('avg_cer'))} / 内容覆盖率 {fmt(s.get('avg_content_recall'))}",
            "color": f"计数准确率 {fmt(s.get('count_accuracy'))} / 召回 {fmt(s.get('avg_recall'))}",
            "template": f"平均IoU {fmt(s.get('avg_iou'))}",
            "detection": f"计数准确率 {fmt(s.get('count_accuracy'))}",
            "draw": f"描边像素命中 {fmt(s.get('probe_hit_rate'))}",
            "image_info": "-",
            "crop": "-",
            "validation": "-",
            "analyze": "-",
        }.get(kind, "-")
        lines.append(
            f"| {kind} | {s['total']} | {s['pass']} | {s['fail']} | {s['skip']} "
            f"| {s['avg_elapsed']:.1f} | {s['max_elapsed']:.1f} | {extra} |"
        )
    lines += ["", "## 明细", ""]
    for r in results:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[r["status"]]
        eng = f" [{r['engine']}]" if r["engine"] else ""
        lines.append(f"### {mark} · {r['id']}{eng}（{r['elapsed']}s）")
        lines.append("")
        lines.append(f"- 详情：{r['detail']}")
        if r["metrics"]:
            lines.append(f"- 指标：{json.dumps(r['metrics'], ensure_ascii=False)}")
        lines.append("")
    (report_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="本地视觉 MCP 基准测试")
    ap.add_argument("--engines", default="auto", help="OCR 引擎，逗号分隔：auto/windows/paddle")
    ap.add_argument("--dataset", default="", help="额外的标准答案 JSON（自己标注的检测数据集）")
    ap.add_argument("--only", default="", help="只跑部分类型，逗号分隔")
    ap.add_argument("--out", default=str(HERE / "report"), help="报告输出目录")
    ap.add_argument("--strict", action="store_true", help="有失败用例时退出码为 1")
    ap.add_argument("--with-ollama", action="store_true", help="额外跑 analyze_image 冒烟测试（需 Ollama + 视觉模型）")
    args = ap.parse_args()

    gt_path = HERE / "generated" / "ground_truth.json"
    if not gt_path.is_file():
        sys.exit(f"找不到 {gt_path}，请先运行：python benchmarks/generate_cases.py")
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    if args.dataset:
        extra = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
        for kind, cases in extra.get("cases", {}).items():
            gt.setdefault("cases", {}).setdefault(kind, []).extend(cases)

    engines = [e.strip().lower() for e in args.engines.split(",") if e.strip()]
    only = {k.strip() for k in args.only.split(",") if k.strip()} if args.only else set()
    report_dir = Path(args.out).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    print(f"加载标准答案：{gt_path}")
    print(f"OCR 引擎：{engines}，仅跑类型：{only or '全部'}")
    results = run_all(gt, engines, only, report_dir, args.with_ollama)
    summary = summarize(results)

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engines": engines,
        "summary": summary,
        "results": results,
    }
    (report_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(results, summary, engines, report_dir)

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    print(f"\n通过 {passed} / {len(results)}，失败 {failed}")
    print(f"报告：{report_dir / 'report.md'}")
    if args.strict and failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
