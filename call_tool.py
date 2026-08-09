#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地视觉工具命令行入口（MCP 工具不可用时的 CLI 兜底）。

调用的是 server.py 里同一批 call_* 函数，结果与 MCP 工具完全等价。

用法：
    python call_tool.py <工具名> '<JSON 参数>'
    python call_tool.py <工具名> --args-file <参数.json>
    echo '<JSON 参数>' | python call_tool.py <工具名>
    python call_tool.py            # 列出可用工具

示例：
    python call_tool.py image_info '{"file_path":"C:/x.png"}'
    python call_tool.py ocr_extract '{"file_path":"C:/x.png","engine":"auto"}'
    python call_tool.py analyze_image '{"file_path":"C:/x.png","mode":"quick"}'

退出码：0 = 成功；1 = 工具报错或参数错误。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402


TOOL_MAP = {
    "analyze_image": server.call_analyze_image,
    "compare_images": server.call_compare_images,
    "image_info": server.call_image_info,
    "ocr_extract": server.call_ocr_extract,
    "detect_objects": server.call_detect_objects,
    "segment_objects": server.call_segment_objects,
    "detect_by_text": server.call_detect_by_text,
    "cv_locate": server.call_cv_locate,
    "crop_image": server.call_crop_image,
    "draw_bounding_box": server.call_draw_box,
    "list_local_models": server.call_list_models,
    "vision_status": server.call_vision_status,
}


USAGE = """本地视觉工具命令行入口（MCP 不可用时的兜底，与 MCP 工具等价）

用法：
  python call_tool.py <工具名> '<JSON 参数>'
  python call_tool.py <工具名> --args-file <参数.json>
  echo '<JSON 参数>' | python call_tool.py <工具名>
  python call_tool.py            # 列出可用工具

示例：
  python call_tool.py image_info '{"file_path":"C:/x.png"}'

可用工具："""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    args = sys.argv[1:]
    if not args:
        print(USAGE + "、".join(TOOL_MAP))
        return 0
    tool = args[0].strip()
    if tool in ("-h", "--help"):
        print(USAGE + "、".join(TOOL_MAP))
        return 0
    fn = TOOL_MAP.get(tool)
    if fn is None:
        print(f"未知工具：{tool}。可用工具：{'、'.join(TOOL_MAP)}", file=sys.stderr)
        print(USAGE + "、".join(TOOL_MAP), file=sys.stderr)
        return 1

    raw = None
    rest = args[1:]
    if rest and rest[0] == "--args-file":
        if len(rest) < 2:
            print("--args-file 需要文件路径", file=sys.stderr)
            return 1
        p = Path(rest[1])
        if not p.is_file():
            print(f"找不到参数文件：{p}", file=sys.stderr)
            return 1
        raw = p.read_text(encoding="utf-8-sig")
    elif rest:
        raw = rest[0]
    elif not sys.stdin.isatty():
        raw = sys.stdin.read().strip()

    if not raw or not raw.strip():
        raw = "{}"
    try:
        call_args = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON 参数解析失败：{e}", file=sys.stderr)
        print("提示：参数请用单引号包裹，例如 '{\"file_path\":\"C:/x.png\"}'", file=sys.stderr)
        return 1
    if not isinstance(call_args, dict):
        print("参数必须是 JSON 对象（键值对）", file=sys.stderr)
        return 1

    try:
        res = fn(call_args)
    except Exception as e:  # noqa: BLE001
        print(f"调用失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if not isinstance(res, dict):
        print(f"返回异常：{res}", file=sys.stderr)
        return 1
    content = res.get("content") or []
    text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
    if res.get("isError"):
        print(text, file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
