"""边界与鲁棒性测试：EXIF 方向、透明图、非法参数、内存保护等。

直接调用 server 函数（不依赖 Ollama / 模型），运行：python tests/test_edge_cases.py
"""

import base64
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import server  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402


def make_rgb(path, w=100, h=100, color="white"):
    Image.new("RGB", (w, h), color).save(path)
    return path


def make_exif_jpg(path, orientation=6, w=100, h=50):
    im = Image.new("RGB", (w, h), "red")
    exif = Image.Exif()
    exif[0x0112] = orientation
    im.save(path, format="JPEG", exif=exif)
    return path


def make_transparent(path, size=40):
    Image.new("RGBA", (size, size), (0, 0, 0, 0)).save(path)
    return path


class TestExifOrientation(unittest.TestCase):
    """手机照片 EXIF 方向：分析/裁切/定位都必须转正。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_load_b64_exif_transposed(self):
        p = make_exif_jpg(os.path.join(self.tmp.name, "rot.jpg"))
        b64, _ = server._load_image_b64(p, 0)
        with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
            self.assertEqual(im.size, (50, 100))

    def test_load_b64_normal_image_stays_raw(self):
        p = make_exif_jpg(os.path.join(self.tmp.name, "normal.jpg"), orientation=1)
        b64, _ = server._load_image_b64(p, 0)
        with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
            self.assertEqual(im.size, (100, 50))

    def test_crop_exif_transposed(self):
        p = make_exif_jpg(os.path.join(self.tmp.name, "rot.jpg"))
        out = os.path.join(self.tmp.name, "crop.png")
        r = server.call_crop_image(
            {"file_path": p, "x1": 0, "y1": 0, "x2": 50, "y2": 100, "output_path": out}
        )
        self.assertFalse(r["isError"], r)
        with Image.open(out) as im:
            self.assertEqual(im.size, (50, 100))

    def test_cv_locate_exif_transposed(self):
        p = make_exif_jpg(os.path.join(self.tmp.name, "rot.jpg"))
        r = server.call_cv_locate({"file_path": p, "mode": "color", "color": "red", "tolerance": 40})
        self.assertFalse(r["isError"], r)
        self.assertIn("50x100", r["content"][0]["text"])


class TestTransparency(unittest.TestCase):
    """透明 PNG：拼图与画框应以白色打底，而不是黑底。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_montage_transparent_white_bg(self):
        tp = make_transparent(os.path.join(self.tmp.name, "t.png"))
        op = make_rgb(os.path.join(self.tmp.name, "o.png"))
        b64 = server._montage_images([tp, op], max_cell=100)
        with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
            px = im.convert("RGB").getpixel((8, 8))  # 第一格左上区域（透明图位置）
            self.assertGreater(px[0], 200, f"透明区域应为白底，实际 {px}")


class TestValidation(unittest.TestCase):
    """非法参数：明确中文报错，不静默降级、不崩溃。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.img = make_rgb(os.path.join(self.tmp.name, "img.png"))
        self.out = os.path.join(self.tmp.name, "out.png")

    def test_parse_color_invalid_raises(self):
        with self.assertRaises(ValueError):
            server._parse_color("gred")

    def test_cv_locate_invalid_color(self):
        r = server.call_cv_locate({"file_path": self.img, "mode": "color", "color": "gred"})
        self.assertTrue(r["isError"])
        self.assertIn("无法识别的颜色", r["content"][0]["text"])

    def test_draw_invalid_color(self):
        boxes = [{"x1": 10, "y1": 10, "x2": 50, "y2": 50, "color": "gred"}]
        r = server.call_draw_box({"image_path": self.img, "boxes": boxes, "output_path": self.out})
        self.assertTrue(r["isError"])
        self.assertIn("无法识别的颜色", r["content"][0]["text"])

    def test_crop_reversed_box(self):
        r = server.call_crop_image(
            {"file_path": self.img, "x1": 80, "y1": 80, "x2": 20, "y2": 20, "output_path": self.out}
        )
        self.assertTrue(r["isError"])
        self.assertIn("x2 必须大于 x1", r["content"][0]["text"])

    def test_draw_reversed_box(self):
        boxes = [{"x1": 80, "y1": 80, "x2": 20, "y2": 20}]
        r = server.call_draw_box({"image_path": self.img, "boxes": boxes, "output_path": self.out})
        self.assertTrue(r["isError"])
        self.assertIn("区域无效", r["content"][0]["text"])

    def test_crop_scale_cap(self):
        # 100x100 放大 100 倍 = 9900x9900 ≈ 98MP，超过 50MP 上限应拒绝
        r = server.call_crop_image(
            {"file_path": self.img, "x1": 0, "y1": 0, "x2": 100, "y2": 100, "scale": 100, "output_path": self.out}
        )
        self.assertTrue(r["isError"])
        self.assertIn("输出过大", r["content"][0]["text"])

    def test_crop_normal_scale_still_works(self):
        r = server.call_crop_image(
            {"file_path": self.img, "x1": 0, "y1": 0, "x2": 50, "y2": 50, "scale": 2, "output_path": self.out}
        )
        self.assertFalse(r["isError"], r)
        with Image.open(self.out) as im:
            self.assertEqual(im.size, (100, 100))

    def test_analyze_empty_file_paths(self):
        r = server.call_analyze_image({"file_paths": []})
        self.assertTrue(r["isError"])

    def test_analyze_file_paths_wrong_type(self):
        # file_paths 传字符串（非数组）应被忽略并给出缺少 file_path 的提示，而不是当多图解析
        r = server.call_analyze_image({"file_paths": "a.png,b.png"})
        self.assertTrue(r["isError"])
        self.assertIn("file_path", r["content"][0]["text"])

    def test_ocr_invalid_engine(self):
        r = server.call_ocr_extract({"file_path": self.img, "engine": "tesseract"})
        self.assertTrue(r["isError"])
        self.assertIn("engine", r["content"][0]["text"])

    def test_cv_locate_invalid_mode(self):
        r = server.call_cv_locate({"file_path": self.img, "mode": "edge"})
        self.assertTrue(r["isError"])
        self.assertIn("mode", r["content"][0]["text"])

    def test_draw_empty_boxes(self):
        r = server.call_draw_box({"image_path": self.img, "boxes": [], "output_path": self.out})
        self.assertTrue(r["isError"])


class TestCvLocateExtremes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.img = make_rgb(os.path.join(self.tmp.name, "img.png"))

    def test_tolerance_zero_and_max(self):
        for tol in (0, 255):
            r = server.call_cv_locate(
                {"file_path": self.img, "mode": "color", "color": "red", "tolerance": tol}
            )
            self.assertFalse(r["isError"], r)

    def test_min_area_huge(self):
        r = server.call_cv_locate(
            {"file_path": self.img, "mode": "color", "color": "red", "min_area": 1e9}
        )
        self.assertFalse(r["isError"], r)

    def test_template_larger_than_image(self):
        tpl = make_rgb(os.path.join(self.tmp.name, "tpl.png"), w=200, h=200)
        r = server.call_cv_locate({"file_path": self.img, "mode": "template", "template_path": tpl})
        self.assertTrue(r["isError"])
        self.assertIn("大于原图", r["content"][0]["text"])


class TestFormats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_image_info_webp(self):
        import PIL.features

        if not PIL.features.check("webp"):
            self.skipTest("Pillow 无 webp 支持")
        p = os.path.join(self.tmp.name, "a.webp")
        Image.new("RGB", (32, 24), "white").save(p, format="WEBP")
        r = server.call_image_info({"file_path": p})
        self.assertFalse(r["isError"], r)
        self.assertIn("格式：WEBP", r["content"][0]["text"])

    def test_image_info_gif(self):
        p = os.path.join(self.tmp.name, "a.gif")
        Image.new("P", (32, 24), 0).save(p, format="GIF")
        r = server.call_image_info({"file_path": p})
        self.assertFalse(r["isError"], r)
        self.assertIn("格式：GIF", r["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
