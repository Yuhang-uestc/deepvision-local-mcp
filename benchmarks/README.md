# 基准测试（Benchmarks）

对本项目的本地视觉工具做**可复现**的量化评测：程序生成带标准答案的合成图片，自动调用工具、计算指标、输出报告。

## 为什么需要它

以前"识图准不准"靠感觉：数人数数对了、某张图 OCR 漏字……没有一个客观数字。有了基准测试：

- 每次改代码都能看到指标变化（变好还是变坏），防止回归；
- 可以在 README 里展示真实的精度数据（不吹不黑）；
- 后续 CI 可以自动跑，坏代码进不了仓库。

## 快速开始

```powershell
cd <项目根目录>
python benchmarks\generate_cases.py    # 生成合成图片 + 标准答案
python benchmarks\run_benchmark.py     # 跑全部用例，输出报告
```

报告输出到 `benchmarks\report\report.md`（人类可读）和 `report.json`（机器可读）。

## 常用参数

| 参数 | 说明 | 示例 |
|---|---|---|
| `--engines` | OCR 引擎，逗号分隔 | `--engines auto` 或 `--engines windows,paddle` |
| `--dataset` | 追加自己标注的检测数据集 | `--dataset benchmarks\datasets\my_photos.json` |
| `--only` | 只跑部分类型 | `--only ocr,color` |
| `--strict` | 有失败用例则退出码为 1（CI 用） | `--strict` |
| `--with-ollama` | 额外跑 analyze_image 冒烟测试（需 Ollama + 视觉模型） | `--with-ollama` |

## 测什么

| 类型 | 默认用例数 | 指标 | 说明 |
|---|---|---|---|
| ocr | 15 | CER、行准确率 | 中/英/混合、表格、小字、深底白字、纯数字、标点、低对比度、彩色文字 |
| color | 12 | 计数准确率、召回率、IoU | 多颜色、多形状、小目标、近色干扰、低容差 |
| template | 3 | 计数、召回、IoU | 单实例 + 同图多实例 |
| image_info | 5 | 尺寸/格式/模式 | PNG / JPEG / BMP / TIFF |
| crop | 4 | 输出尺寸 + 像素一致 | 绝对坐标、放大、归一化坐标、外扩边距 |
| draw | 2 | 框数量 + 描边像素 | 边界框绘制是否正确落在像素上 |
| validation | 6 | 非法输入是否被拒绝 | 缺失文件 / 伪格式 / 相对路径 / 空文件 / 目录 / 扩展名与内容不符 |
| analyze | 1（可选） | 是否成功返回 | 本地视觉模型端到端冒烟（`--with-ollama`） |

指标口径：

- **CER**：字符错误率 = 编辑距离 ÷ 字符数（中文去空白、全角转半角后计算）；
- **内容覆盖率**：标准答案每行文字是否完整出现在识别结果中（容忍 OCR 换行/分栏差异）；
- **IoU**：预测框与标准框的交并比；
- **计数准确率**：期望数量与检出数量一致的用例占比。

## 怎么测自己的照片（检测 / 计数）

合成图测不了 YOLO 真人检测，所以留了自定义数据集入口。新建一个 JSON（例如 `benchmarks\datasets\my_photos.json`）：

```json
{
  "cases": {
    "detection": [
      {
        "id": "my_group_photo",
        "file": "benchmarks/datasets/my_group_photo.jpg",
        "tool": "detect_objects",
        "model": "yolov8n.pt",
        "classes": ["person"],
        "expected_count": 20
      }
    ]
  }
}
```

然后运行：

```powershell
python benchmarks\run_benchmark.py --dataset benchmarks\datasets\my_photos.json
```

注意：自己标注的照片**不要提交进仓库**（真人照片默认被 .gitignore 屏蔽）。

## 注意事项

- 合成用例固定随机种子，同一台机器每次结果一致；中文用例依赖系统 CJK 字体（Windows 自带微软雅黑），没有字体的机器会自动跳过中文用例并在报告中说明。
- 基准测试结果就是工具的真实水平。比如 Windows OCR 曾把"金额"识别成"全额"、把字母 O 读成数字 0、把"新"拆成"亲斤"，这类失败是真实的质量数据，不要为了好看改阈值掩盖。
- `--with-ollama` 跑的是冒烟测试（能出结果即可），不校验内容准确率——视觉模型的语义准确率难以用合成图做标准答案，需要的话可以用 `--dataset` 挂人工标注的真实照片。
- 若你的进程对 `%USERPROFILE%\.paddlex` 无写权限（沙盒 / 受限环境），`auto` 引擎会初始化 PaddleOCR 失败并自动回退 Windows OCR，报告中体现的就是 Windows OCR 的水平；此时要测 PaddleOCR 需在普通终端运行。
- `benchmarks\generated` 和 `benchmarks\report` 默认不提交，随时可用生成器重建。
