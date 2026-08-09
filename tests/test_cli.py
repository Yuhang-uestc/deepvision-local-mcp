"""call_tool.py CLI 兜底的测试。

运行：python tests/test_cli.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "call_tool.py"
PY = sys.executable


def run(*args, stdin=None):
    return subprocess.run(
        [PY, str(CLI), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=stdin,
    )


def make_png(path, w=20, h=10):
    from PIL import Image

    Image.new("RGB", (w, h), "white").save(path)
    return str(path)


class TestCli(unittest.TestCase):
    def test_usage_lists_tools(self):
        r = run()
        self.assertEqual(r.returncode, 0)
        for t in ("analyze_image", "ocr_extract", "compare_images", "vision_status", "cv_locate"):
            self.assertIn(t, r.stdout)

    def test_help(self):
        r = run("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("用法", r.stdout)

    def test_unknown_tool(self):
        r = run("no_such_tool")
        self.assertEqual(r.returncode, 1)
        self.assertIn("未知工具", r.stderr)

    def test_bad_json(self):
        r = run("image_info", "{bad json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("JSON", r.stderr)

    def test_non_object_json(self):
        r = run("image_info", "[1,2,3]")
        self.assertEqual(r.returncode, 1)
        self.assertIn("JSON 对象", r.stderr)

    def test_image_info_direct_arg(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_png(os.path.join(d, "a.png"))
            r = run("image_info", json.dumps({"file_path": p}))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("尺寸：20 x 10", r.stdout)

    def test_image_info_args_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_png(os.path.join(d, "a.png"), w=5, h=5)
            af = os.path.join(d, "args.json")
            Path(af).write_text(json.dumps({"file_path": p}), encoding="utf-8")
            r = run("image_info", "--args-file", af)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("尺寸：5 x 5", r.stdout)

    def test_image_info_stdin(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_png(os.path.join(d, "a.png"), w=7, h=7)
            r = run("image_info", stdin=json.dumps({"file_path": p}))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("尺寸：7 x 7", r.stdout)

    def test_tool_error_goes_to_stderr(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_png(os.path.join(d, "a.png"))
            r = run("ocr_extract", json.dumps({"file_path": p, "engine": "tesseract"}))
            self.assertEqual(r.returncode, 1)
            self.assertIn("engine", r.stderr)

    def test_missing_args_file(self):
        r = run("image_info", "--args-file", "C:/no/such/file.json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("找不到参数文件", r.stderr)

    def test_missing_file_path(self):
        r = run("image_info", "{}")
        self.assertEqual(r.returncode, 1)
        self.assertIn("file_path", r.stderr)


if __name__ == "__main__":
    unittest.main()
