# v2.3.0 本地识图 MCP：DeepSeek 看图 + 多图支持

给 DeepSeek 等纯文本模型补上本地"看图"能力：Ollama 视觉模型描述 + PaddleOCR 文字识别 + YOLO 检测/分割 + 零样本检测 + 颜色/模板定位 + 裁切放大 + 多图逐张/拼图对比，图片全程不出本机。

## 功能总览（12 个工具）

- `analyze_image`：本地视觉模型看图；`file_paths` 多图自动**逐张完整分析**后合并返回（图1/图2…标签），quick / detailed 双模式
- `compare_images`：**新增**。用户明确要求"对比 / 有什么区别"时，多图按编号拼成网格、一次分析异同
- `ocr_extract`：PaddleOCR 场景文字识别（含坐标框），未装自动回退 Windows OCR
- `detect_objects` / `segment_objects` / `detect_by_text`：YOLO 检测 / 分割 / 零样本检测
- `cv_locate`：颜色分割 / 模板匹配定位，不依赖深度学习模型
- `crop_image` / `draw_bounding_box` / `image_info`：裁切放大、画框验证、尺寸信息
- `list_local_models` / `vision_status`：模型列表与一键排障

## v2.3.0 更新内容

**新增**

- 多图支持：`analyze_image(file_paths=[...])` 逐张独立分析后合并返回，不再静默丢弃第二张
- `compare_images` 对比工具：多图拼成带编号的网格图，一次分析异同（拼接会缩小单图，细节请逐张分析）
- 基准测试套件：47 个合成用例 + 指标报告（OCR / 颜色定位 / 模板匹配 / 裁切 / 输入校验），可复现
- 英文 README（README.en.md）+ 首页英文简介；中文 Issue 模板；ROADMAP
- 边界与纵深测试：`test_edge_cases.py`（22 项）+ `test_robustness.py`（28 项），全量 87 项离线测试

**修复**

- EXIF 方向：手机竖拍照片在分析 / 裁切 / 定位中自动转正
- 非法颜色明确报错，不再静默降级为红色
- `crop_image` 放大输出上限 50MP，防止内存被撑爆
- 裁切右 / 下边界允许取到 w/h（原来永远少 1 像素）
- 透明 PNG 在拼图 / 画框中以白色打底，不再黑底
- `OLLAMA_HOST` 带路径（如代理地址）时端口追加错位
- PaddleOCR 结果解析器对畸形条目逐条防御，不再整页失败

**测试**

- 87 项离线测试全部通过；基准 44/47（3 个失败为 Windows OCR 真实误读：金额→全额、O→0、新→亲斤）

## 快速上手

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1 -Extras
```

## 文档

- 部署与常见问题：https://github.com/Yuhang-uestc/deepvision-local-mcp/blob/master/docs/部署与常见问题.md
- 架构说明：https://github.com/Yuhang-uestc/deepvision-local-mcp/blob/master/docs/架构说明.md
- Roadmap：https://github.com/Yuhang-uestc/deepvision-local-mcp/blob/master/ROADMAP.md

## 许可

- 项目代码：MIT License
- 模型权重（yolov8*.pt 等）为 Ultralytics AGPL-3.0 许可，首次调用自动下载，不随仓库分发
