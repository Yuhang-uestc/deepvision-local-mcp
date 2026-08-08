# -*- coding: utf-8 -*-
"""零样本检测中英文对照实测脚本。

用法：python examples/test_zeroshot_cn.py <图片绝对路径>
会用英文/中文描述依次检测常见物体，打印结果，用于确认中文零样本描述是否可用。

注意：图片请选有常见物体（人/车/狗/猫等）的普通照片，不要用私密证件照。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server


def main():
    if len(sys.argv) < 2:
        print("用法：python examples/test_zeroshot_cn.py <图片绝对路径>")
        return
    img = sys.argv[1]
    if not Path(img).is_file():
        print("找不到图片：", img)
        return
    pairs = [
        ("person", "人"),
        ("dog", "狗"),
        ("cat", "猫"),
        ("car", "车"),
        ("chair", "椅子"),
        ("bottle", "瓶子"),
        ("blue tent", "蓝色帐篷"),
    ]
    print("测试图片：", img)
    print("=" * 50)
    for en, cn in pairs:
        for label, text in (("EN", en), ("CN", cn)):
            r = server.call_detect_by_text(
                {
                    "file_path": img,
                    "text": text,
                    "model": "yolov8s-world.pt",
                    "min_confidence": 0.15,
                }
            )
            txt = r["content"][0]["text"]
            first = txt.splitlines()[0] if txt else ""
            print(f"{label:>2} {text:<8} -> {first}")
    print("=" * 50)
    print("判断：若 EN 能检出而 CN 报'未检测到'，说明中文零样本不可用，文案示例应改用英文。")


if __name__ == "__main__":
    main()
