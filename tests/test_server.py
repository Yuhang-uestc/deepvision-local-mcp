"""local_vision MCP server 的离线测试：用 mock Ollama 验证协议与工具。

运行：python tests/test_server.py
覆盖：tools/list、analyze_image（mock）、image_info、crop_image、
      draw_bounding_box（多框）、cv_locate（颜色/模板）、错误路径、输出目录限制。
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(ROOT, "server.py")

CANNED = "模拟视觉模型输出：画面主体是一个蓝色方块，右上有白色文字 HELLO。"


class MockHandler(BaseHTTPRequestHandler):
    # 类级计数器：用于验证缓存命中与重试行为
    generate_calls = 0
    fail_first_generate = 0

    def log_message(self, *args):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "qwen3-vl:8b"}]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/generate":
            MockHandler.generate_calls += 1
            if MockHandler.fail_first_generate > 0:
                MockHandler.fail_first_generate -= 1
                self._send({"error": "internal error"}, 500)
                return
            n = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(n) if n else b""
            try:
                payload = json.loads(body.decode("utf-8"))
                model = payload.get("model", "")
            except Exception:
                model = ""
            if model == "qwen3-vl:4b":
                self._send({"error": "model not found"}, 404)
                return
            self._send({"response": CANNED})
        else:
            self._send({"error": "not found"}, 404)


class McpClient:
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

    def _roundtrip(self, msg):
        self._id += 1
        msg = dict(msg)
        msg["id"] = self._id
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout unexpectedly")
        return json.loads(line)

    def init(self):
        return self._roundtrip(
            {"jsonrpc": "2.0", "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
        )

    def tools(self):
        return self._roundtrip({"jsonrpc": "2.0", "method": "tools/list"})

    def call(self, name, arguments):
        return self._roundtrip(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )

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


def make_image(path, w=320, h=240):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 80, 160, 140], fill="red")
    draw.rectangle([200, 30, 260, 70], fill="blue")
    draw.text((30, 190), "HELLO", fill="black")
    img.save(path)
    return path


class TestLocalVision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._httpd = HTTPServer(("127.0.0.1", 0), MockHandler)
        cls._thread = threading.Thread(target=cls._httpd.serve_forever, daemon=True)
        cls._thread.start()
        cls.port = cls._httpd.server_address[1]
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = os.environ.copy()
        cls.env["OLLAMA_HOST"] = f"http://127.0.0.1:{cls.port}"
        cls.env["PYTHONIOENCODING"] = "utf-8"
        cls.env["LOCAL_VISION_RETRY_BASE"] = "0.1"  # 测试里重试退避不等待
        cls.client = McpClient(cls.env)
        cls.client.init()
        cls.test_img = make_image(os.path.join(cls.tmp.name, "test.png"))

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls._httpd.shutdown()
        cls._httpd.server_close()
        cls.tmp.cleanup()

    def result(self, resp):
        self.assertIn("result", resp)
        return resp["result"]

    def test_tools_list(self):
        names = [t["name"] for t in self.result(self.client.tools())["tools"]]
        for need in (
            "analyze_image",
            "image_info",
            "ocr_extract",
            "detect_objects",
            "segment_objects",
            "detect_by_text",
            "cv_locate",
            "crop_image",
            "draw_bounding_box",
            "list_local_models",
            "vision_status",
        ):
            self.assertIn(need, names)

    def test_analyze_image_mock(self):
        r = self.result(self.client.call("analyze_image", {"file_path": self.test_img}))
        self.assertFalse(r["isError"])
        self.assertIn("模拟视觉模型", r["content"][0]["text"])
        self.assertTrue(r["content"][0]["text"].startswith("[安全提示]"))

    def test_analyze_cache_hit(self):
        # 相同图片 + 相同 prompt 第二次调用应命中缓存，不再请求 Ollama
        prompt = "cache-hit-test"
        before = MockHandler.generate_calls
        for _ in range(2):
            r = self.result(
                self.client.call("analyze_image", {"file_path": self.test_img, "prompt": prompt})
            )
            self.assertFalse(r["isError"])
        self.assertLessEqual(MockHandler.generate_calls - before, 1)

    def test_ollama_retry_transient_500(self):
        # 首次请求返回 500，应自动重试成功（不报错且请求数 >= 2）
        MockHandler.fail_first_generate = 1
        try:
            before = MockHandler.generate_calls
            r = self.result(
                self.client.call(
                    "analyze_image", {"file_path": self.test_img, "prompt": "retry-transient-test"}
                )
            )
            self.assertFalse(r["isError"], r)
            self.assertGreaterEqual(MockHandler.generate_calls - before, 2)
        finally:
            MockHandler.fail_first_generate = 0

    def test_vision_status(self):
        r = self.result(self.client.call("vision_status", {}))
        self.assertFalse(r["isError"])
        text = r["content"][0]["text"]
        self.assertIn("服务器版本", text)
        self.assertIn("qwen3-vl:8b", text)
        self.assertIn("Ollama", text)
        self.assertIn("缓存", text)

    def test_analyze_multi_image_mock(self):
        r = self.result(
            self.client.call(
                "analyze_image",
                {"file_paths": [self.test_img, self.test_img], "prompt": "对比这两张图"},
            )
        )
        self.assertFalse(r["isError"])

    def test_analyze_quick_fallback(self):
        # quick 模式默认 qwen3-vl:4b，mock 返回 404，应自动回退 qwen3-vl:8b
        r = self.result(self.client.call("analyze_image", {"file_path": self.test_img, "mode": "quick"}))
        self.assertFalse(r["isError"], r)
        self.assertIn("模拟视觉模型", r["content"][0]["text"])

    def test_image_info(self):
        r = self.result(self.client.call("image_info", {"file_path": self.test_img}))
        self.assertFalse(r["isError"])
        text = r["content"][0]["text"]
        self.assertIn("320", text)
        self.assertIn("240", text)

    def test_list_models(self):
        r = self.result(self.client.call("list_local_models", {}))
        self.assertFalse(r["isError"])
        self.assertIn("qwen3-vl:8b", r["content"][0]["text"])

    def test_crop_and_scale(self):
        out = os.path.join(self.tmp.name, "crop.png")
        r = self.result(
            self.client.call(
                "crop_image",
                {
                    "file_path": self.test_img,
                    "output_path": out,
                    "x1": 90,
                    "y1": 70,
                    "x2": 170,
                    "y2": 150,
                    "scale": 2,
                },
            )
        )
        self.assertFalse(r["isError"], r)
        self.assertTrue(os.path.isfile(out))
        from PIL import Image

        with Image.open(out) as im:
            self.assertEqual(im.size, (160, 160))

    def test_draw_multi_boxes(self):
        out = os.path.join(self.tmp.name, "boxes.png")
        boxes = [
            {"x1": 95, "y1": 75, "x2": 165, "y2": 145, "label": "目标A", "color": "#00ff00"},
            {"x1": 195, "y1": 25, "x2": 265, "y2": 75, "label": "目标B", "color": "blue"},
        ]
        r = self.result(
            self.client.call(
                "draw_bounding_box",
                {"image_path": self.test_img, "output_path": out, "boxes": boxes},
            )
        )
        self.assertFalse(r["isError"], r)
        self.assertTrue(os.path.isfile(out))
        self.assertIn("2 个边界框", r["content"][0]["text"])

    def test_cv_locate_color(self):
        r = self.result(
            self.client.call(
                "cv_locate",
                {"file_path": self.test_img, "mode": "color", "color": "#ff0000"},
            )
        )
        self.assertFalse(r["isError"], r)
        text = r["content"][0]["text"]
        self.assertIn("100", text)

    def test_cv_locate_template(self):
        from PIL import Image

        tpl = os.path.join(self.tmp.name, "tpl.png")
        with Image.open(self.test_img) as im:
            # 带白色边缘的模板（含纹理），避免纯色模板导致归一化匹配退化
            im.crop((90, 70, 170, 150)).save(tpl)
        r = self.result(
            self.client.call(
                "cv_locate",
                {
                    "file_path": self.test_img,
                    "mode": "template",
                    "template_path": tpl,
                    "threshold": 0.8,
                },
            )
        )
        self.assertFalse(r["isError"], r)
        self.assertIn("90", r["content"][0]["text"])

    def test_segment_missing_file_error(self):
        r = self.result(self.client.call("segment_objects", {"file_path": "Z:/no/such.png"}))
        self.assertTrue(r["isError"])

    def test_ocr_paddle_not_installed(self):
        try:
            import paddleocr  # noqa: F401

            self.skipTest("PaddleOCR 已安装，跳过未安装场景测试")
        except ImportError:
            pass
        r = self.result(self.client.call("ocr_extract", {"file_path": self.test_img, "engine": "paddle"}))
        self.assertTrue(r["isError"])
        self.assertIn("PaddleOCR", r["content"][0]["text"])

    def test_missing_file_error(self):
        r = self.result(self.client.call("analyze_image", {"file_path": "Z:/no/such.png"}))
        self.assertTrue(r["isError"])

    def test_crop_invalid_region_error(self):
        r = self.result(
            self.client.call(
                "crop_image",
                {"file_path": self.test_img, "x1": 200, "y1": 100, "x2": 100, "y2": 200},
            )
        )
        self.assertTrue(r["isError"])

    def test_output_dir_enforced(self):
        env = dict(self.env)
        env["VISION_OUTPUT_DIR"] = self.tmp.name
        outside = os.path.join(os.path.dirname(self.tmp.name), "outside_v2.png")
        c = McpClient(env)
        try:
            c.init()
            r = self.result(
                c.call(
                    "draw_bounding_box",
                    {
                        "image_path": self.test_img,
                        "output_path": outside,
                        "x1": 0,
                        "y1": 0,
                        "x2": 50,
                        "y2": 50,
                    },
                )
            )
            self.assertTrue(r["isError"])
            self.assertIn("VISION_OUTPUT_DIR", r["content"][0]["text"])
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
