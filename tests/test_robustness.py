"""纵深鲁棒性测试：缓存、主机归一化、解析器、格式化、拼图极端、协议 schema。

直接调用 server / benchmarks 的纯函数与工具函数，不依赖 Ollama 与模型。
运行：python tests/test_robustness.py
"""

import base64
import importlib.util
import io
import os
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import server  # noqa: E402
from PIL import Image  # noqa: E402


def load_benchmark_module():
    path = os.path.join(ROOT, "benchmarks", "run_benchmark.py")
    spec = importlib.util.spec_from_file_location("benchmark_runner", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_exif_jpg(path, orientation=6, w=100, h=50):
    im = Image.new("RGB", (w, h), "red")
    exif = Image.Exif()
    exif[0x0112] = orientation
    im.save(path, format="JPEG", exif=exif)
    return path


class TestHostNormalization(unittest.TestCase):
    def test_cases(self):
        cases = [
            ("", "http://localhost:11434"),
            ("localhost", "http://localhost:11434"),
            ("localhost:12345", "http://localhost:12345"),
            ("0.0.0.0", "http://127.0.0.1:11434"),
            ("0.0.0.0:12345", "http://127.0.0.1:12345"),
            ("http://localhost:11434/", "http://localhost:11434"),
            ("http://localhost", "http://localhost:11434"),
            ("127.0.0.1:11434/api", "http://127.0.0.1:11434/api"),
            ("https://host/api", "https://host:11434/api"),
            ("https://host:8080/api", "https://host:8080/api"),
            ("http://127.0.0.1", "http://127.0.0.1:11434"),
        ]
        for raw, expected in cases:
            self.assertEqual(server._normalize_ollama_host(raw), expected, f"raw={raw!r}")


class TestCache(unittest.TestCase):
    def setUp(self):
        self._orig_cache = server._CACHE
        self._orig_max = server.LOCAL_VISION_CACHE_MAX
        self._orig_ttl = server.LOCAL_VISION_CACHE_TTL
        self._orig_enabled = server.LOCAL_VISION_CACHE
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def tearDown(self):
        server._CACHE.clear()
        server.LOCAL_VISION_CACHE = self._orig_enabled
        server.LOCAL_VISION_CACHE_MAX = self._orig_max
        server.LOCAL_VISION_CACHE_TTL = self._orig_ttl

    def test_roundtrip(self):
        server.LOCAL_VISION_CACHE = True
        key = ("k",)
        server._cache_put(key, "v")
        self.assertEqual(server._cache_get(key), "v")

    def test_ttl_expiry(self):
        server.LOCAL_VISION_CACHE = True
        server.LOCAL_VISION_CACHE_TTL = -1
        key = ("k",)
        server._cache_put(key, "v")
        self.assertIsNone(server._cache_get(key))

    def test_max_eviction(self):
        server.LOCAL_VISION_CACHE = True
        server.LOCAL_VISION_CACHE_MAX = 2
        server._cache_put(("a",), 1)
        server._cache_put(("b",), 2)
        server._cache_put(("c",), 3)
        self.assertEqual(len(server._CACHE), 2)
        self.assertIsNone(server._cache_get(("a",)))

    def test_disabled(self):
        server.LOCAL_VISION_CACHE = False
        key = ("k",)
        server._cache_put(key, "v")
        self.assertIsNone(server._cache_get(key))

    def test_content_digest_same_content(self):
        p1 = os.path.join(self.tmp.name, "a.png")
        p2 = os.path.join(self.tmp.name, "b.png")
        data = b"same-bytes"
        open(p1, "wb").write(data)
        open(p2, "wb").write(data)
        self.assertEqual(server._content_digest([p1]), server._content_digest([p2]))
        open(p1, "wb").write(b"changed")
        self.assertNotEqual(server._content_digest([p1]), server._content_digest([p2]))

    def test_concurrent_access(self):
        server.LOCAL_VISION_CACHE = True
        errors = []

        def worker(n):
            try:
                for i in range(50):
                    key = (f"k{n}", i)
                    server._cache_put(key, i)
                    server._cache_get(key)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


class TestPaddleParsers(unittest.TestCase):
    def test_v2_empty(self):
        self.assertEqual(server._parse_paddle_v2(None), [])
        self.assertEqual(server._parse_paddle_v2([]), [])

    def test_v2_valid(self):
        result = [[[ [[0, 0], [10, 0], [10, 10], [0, 10]], ("hello", 0.9) ]]]
        lines = server._parse_paddle_v2(result)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["text"], "hello")
        self.assertEqual(lines[0]["x"], 0)
        self.assertEqual(lines[0]["w"], 10)
        self.assertEqual(lines[0]["confidence"], 0.9)

    def test_v2_malformed_skipped(self):
        result = [[["not-a-box"], ("t", 0.5)]]
        self.assertEqual(server._parse_paddle_v2(result), [])

    def test_v3_empty_and_missing_keys(self):
        self.assertEqual(server._parse_paddle_v3(None), [])
        self.assertEqual(server._parse_paddle_v3([{}]), [])
        self.assertEqual(server._parse_paddle_v3([{"rec_texts": ["a"]}]), [])

    def test_v3_valid(self):
        result = [
            {
                "rec_texts": ["a", "b"],
                "rec_polys": [[[0, 0], [10, 0], [10, 10], [0, 10]], [[5, 5], [15, 5], [15, 15], [5, 15]]],
                "rec_scores": [0.8, 0.7],
            }
        ]
        lines = server._parse_paddle_v3(result)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1]["text"], "b")
        self.assertEqual(lines[1]["confidence"], 0.7)

    def test_v3_polys_shorter_than_texts(self):
        result = [{"rec_texts": ["a", "b", "c"], "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}]
        self.assertEqual(len(server._parse_paddle_v3(result)), 1)


class _XYXY:
    def __init__(self, vals):
        self.vals = vals

    def tolist(self):
        return self.vals


class _FakeBox:
    def __init__(self, xyxy, conf, cls):
        self.xyxy = [_XYXY(xyxy)]
        self.conf = [conf]
        self.cls = [cls]


class _FakeResult:
    def __init__(self, boxes=None, orig_shape=(240, 320), names=None):
        self.boxes = boxes
        self.orig_shape = orig_shape
        self.names = names


class TestDetectionFormat(unittest.TestCase):
    def test_empty_boxes(self):
        r, msg = server._format_detection_results([_FakeResult(boxes=None)])
        self.assertIsNone(r)
        self.assertIn("未检测到任何目标", msg)

    def test_valid_boxes_dict_names(self):
        res = _FakeResult(
            boxes=[_FakeBox([10, 20, 110, 220], 0.95, 0)],
            names={0: "person"},
        )
        r, msg = server._format_detection_results([res])
        self.assertIsNotNone(r)
        self.assertIn("person (0.95)", msg)
        self.assertIn("像素框 [10.0,20.0,110.0,220.0]", msg)

    def test_class_name_out_of_range(self):
        self.assertEqual(server._class_name([], 99), "99")
        self.assertEqual(server._class_name({}, 99), "99")


class TestMontageExtremes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _img(self, name, w=100, h=100, color="white"):
        p = os.path.join(self.tmp.name, name)
        Image.new("RGB", (w, h), color).save(p)
        return p

    def test_nine_images(self):
        paths = [self._img(f"{i}.png") for i in range(9)]
        b64 = server._montage_images(paths, max_cell=200)
        with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
            self.assertGreater(im.size[0], 0)
            self.assertGreater(im.size[1], 0)

    def test_extreme_aspect_ratios(self):
        pan = self._img("pan.png", w=2000, h=100)
        tall = self._img("tall.png", w=100, h=2000)
        b64 = server._montage_images([pan, tall], max_cell=400)
        with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
            self.assertLessEqual(im.size[0], 2 * 400 + 3 * 12)

    def test_ten_images_two_digit_labels(self):
        paths = [self._img(f"{i}.png") for i in range(10)]
        b64 = server._montage_images(paths, max_cell=100)
        self.assertTrue(b64)

    def test_exif_in_montage(self):
        rot = make_exif_jpg(os.path.join(self.tmp.name, "rot.jpg"))
        normal = self._img("n.png", w=50, h=50)
        b64 = server._montage_images([rot, normal], max_cell=200)
        self.assertTrue(b64)


class TestToolSchema(unittest.TestCase):
    def test_tool_count_and_schema(self):
        self.assertEqual(len(server.TOOLS), 12)
        for tool in server.TOOLS:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            schema = tool["inputSchema"]
            self.assertEqual(schema.get("type"), "object")
            self.assertIsInstance(schema.get("properties"), dict)
            if schema.get("properties"):
                self.assertIn("required", schema, tool["name"])


class TestOutputProtection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.img = os.path.join(self.tmp.name, "img.png")
        Image.new("RGB", (100, 100), "white").save(self.img)

    def test_draw_output_equals_input_rejected(self):
        boxes = [{"x1": 10, "y1": 10, "x2": 50, "y2": 50}]
        r = server.call_draw_box({"image_path": self.img, "boxes": boxes, "output_path": self.img})
        self.assertTrue(r["isError"])
        self.assertIn("不能覆盖", r["content"][0]["text"])

    def test_crop_output_equals_input_rejected(self):
        r = server.call_crop_image(
            {"file_path": self.img, "x1": 0, "y1": 0, "x2": 50, "y2": 50, "output_path": self.img}
        )
        self.assertTrue(r["isError"])
        self.assertIn("不能覆盖", r["content"][0]["text"])


class TestAnalyzeMultiCorrupt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.valid = os.path.join(self.tmp.name, "ok.png")
        Image.new("RGB", (10, 10), "white").save(self.valid)
        self.fake = os.path.join(self.tmp.name, "fake.png")
        open(self.fake, "wb").write(b"not an image")

    def test_second_image_invalid_reports_clear_error(self):
        r = server.call_analyze_image({"file_paths": [self.valid, self.fake]})
        self.assertTrue(r["isError"])
        self.assertIn("fake.png", r["content"][0]["text"])


class TestBenchmarkUtils(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bm = load_benchmark_module()

    def test_levenshtein(self):
        self.assertEqual(self.bm.levenshtein("", ""), 0)
        self.assertEqual(self.bm.levenshtein("abc", "abc"), 0)
        self.assertEqual(self.bm.levenshtein("abc", "abd"), 1)
        self.assertEqual(self.bm.levenshtein("kitten", "sitting"), 3)

    def test_parse_ocr_lines(self):
        text = "OCR 识别文字（PaddleOCR）：\nhello world\n\n文本块位置：\n- [0,0,10x10] hello world"
        self.assertEqual(self.bm.parse_ocr_lines(text), ["hello world"])
        self.assertEqual(self.bm.parse_ocr_lines("PaddleOCR：图中未识别到文字。"), [])

    def test_parse_boxes(self):
        text = "颜色定位（#ff0000，容差 40）：找到 2 个区域（图片 10x10）：\n- 区域1：像素框 [1,2,3,4]，归一化 [0.1,0.2,0.3,0.4]，面积 4px\n- 区域2：像素框 [5,6,7,8]，归一化 [0.5,0.6,0.7,0.8]，面积 4px"
        self.assertEqual(self.bm.parse_boxes(text), [[1, 2, 3, 4], [5, 6, 7, 8]])

    def test_eval_boxes(self):
        gt = [[0, 0, 10, 10]]
        pred = [[0, 0, 10, 10]]
        m = self.bm.eval_boxes(gt, pred)
        self.assertEqual(m["count_gt"], 1)
        self.assertEqual(m["recall"], 1.0)


class TestPaddleCacheRedirect(unittest.TestCase):
    """PaddleX 缓存自动重定向：默认缓存不可写时改到可写目录，尊重用户显式设置。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._env_backup = os.environ.get("PADDLE_PDX_CACHE_HOME")
        os.environ.pop("PADDLE_PDX_CACHE_HOME", None)

    def tearDown(self):
        if self._env_backup is None:
            os.environ.pop("PADDLE_PDX_CACHE_HOME", None)
        else:
            os.environ["PADDLE_PDX_CACHE_HOME"] = self._env_backup

    def test_writable_default_no_change(self):
        ok_dir = os.path.join(self.tmp.name, "ok")
        os.makedirs(ok_dir)
        server._ensure_paddle_cache_writable(default_cache=ok_dir)
        self.assertNotIn("PADDLE_PDX_CACHE_HOME", os.environ)

    def test_unwritable_default_redirects(self):
        # 用一个"文件"冒充目录，写入必然失败 -> 触发重定向
        blocked = os.path.join(self.tmp.name, "blocked")
        open(blocked, "w").write("x")
        server._ensure_paddle_cache_writable(default_cache=blocked)
        redirected = os.environ.get("PADDLE_PDX_CACHE_HOME")
        self.assertTrue(redirected, "应自动重定向")
        self.assertTrue(os.path.isdir(redirected))
        probe = os.path.join(redirected, ".probe")
        open(probe, "w").write("x")
        os.unlink(probe)

    def test_explicit_env_respected(self):
        os.environ["PADDLE_PDX_CACHE_HOME"] = "D:/my_cache"
        server._ensure_paddle_cache_writable(default_cache=os.path.join(self.tmp.name, "nope"))
        self.assertEqual(os.environ["PADDLE_PDX_CACHE_HOME"], "D:/my_cache")


if __name__ == "__main__":
    unittest.main()
