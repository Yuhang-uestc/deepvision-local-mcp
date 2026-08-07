"""真机端到端冒烟测试（需要本机 Ollama 已启动且已有 qwen3-vl 模型）。

用法：
  python tests/e2e_smoke.py                 # 快速：不含慢速视觉模型分析
  python tests/e2e_smoke.py --analyze       # 含 analyze_image（8B 模型约 20-60 秒）

会向本机 Ollama 发送图片并调用 YOLO，全程本地处理。
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(ROOT, "server.py")
OUTDIR = os.path.join(ROOT, "outputs")


class Client:
    def __init__(self, env):
        self.proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def tool(self, name, args):
        r = self.call("tools/call", {"name": name, "arguments": args})
        res = r.get("result", {})
        text = res.get("content", [{}])[0].get("text", "")
        tag = "OK" if not res.get("isError") else "ERR"
        print(f"--- {name} ---")
        print(f"[{tag}] {text[:800]}")
        print()
        return res

    def close(self):
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            pass
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.stdout.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze", action="store_true", help="包含慢速视觉模型分析")
    ap.add_argument("--image", default=os.path.join(ROOT, "examples", "demo_input.png"), help="测试图片")
    ap.add_argument("--people", default=os.path.join(ROOT, "detected_people.png"), help="人物照片（数人测试）")
    args = ap.parse_args()

    env = os.environ.copy()
    env["OLLAMA_HOST"] = "http://localhost:11434"
    env["PYTHONIOENCODING"] = "utf-8"
    os.makedirs(OUTDIR, exist_ok=True)

    c = Client(env)
    try:
        c.call("initialize", {"protocolVersion": "2025-06-18"})
        img = args.image
        people = args.people

        c.tool("image_info", {"file_path": img})
        c.tool("cv_locate", {"file_path": img, "mode": "color", "color": "#16a34a", "tolerance": 28})
        c.tool(
            "crop_image",
            {
                "file_path": img,
                "output_path": os.path.join(OUTDIR, "e2e_crop.png"),
                "x1": 560,
                "y1": 40,
                "x2": 760,
                "y2": 260,
                "scale": 2,
            },
        )
        if os.path.isfile(people):
            c.tool(
                "detect_objects",
                {
                    "file_path": people,
                    "classes": ["person"],
                    "min_confidence": 0.5,
                    "save_path": os.path.join(OUTDIR, "e2e_people.png"),
                },
            )
        c.tool(
            "draw_bounding_box",
            {
                "image_path": img,
                "output_path": os.path.join(OUTDIR, "e2e_boxes_cn.png"),
                "boxes": [
                    {"x1": 61, "y1": 121, "x2": 240, "y2": 300, "label": "水体", "color": "#00aaff"},
                    {"x1": 300, "y1": 80, "x2": 500, "y2": 260, "label": "农田", "color": "#ffaa00"},
                ],
                "line_width": 6,
            },
        )
        c.tool("ocr_extract", {"file_path": img})
        if args.analyze:
            t0 = time.time()
            c.tool(
                "analyze_image",
                {
                    "file_path": os.path.join(OUTDIR, "e2e_crop.png"),
                    "prompt": "用一句话描述这张图的内容",
                },
            )
            print(f"(analyze 耗时 {time.time() - t0:.0f}s)")
    finally:
        c.close()


if __name__ == "__main__":
    main()
