给 DeepSeek 等纯文本模型补上本地"看图"能力：Ollama 视觉模型描述 + PaddleOCR 文字识别 + YOLO 检测/分割 + 零样本检测 + 颜色/模板定位 + 裁切放大，图片全程不出本机。

## 功能总览（11 个工具）

- `analyze_image`：本地视觉模型看图，quick / detailed 双模式（默认 4B / 8B，自动回退）
- `ocr_extract`：PaddleOCR 场景文字识别（含坐标框），未装时自动回退 Windows OCR
- `detect_objects`：YOLO 检测 COCO 80 类常见物体
- `segment_objects`：YOLO 像素级分割，遮挡数人 / 面积量算
- `detect_by_text`：YOLOE / YOLO-World 零样本检测，用文字描述找任意物体
- `cv_locate`：颜色分割 / 模板匹配定位，不依赖深度学习模型
- `crop_image` / `draw_bounding_box` / `image_info`：裁切放大、画框验证、尺寸信息
- `list_local_models` / `vision_status`：模型列表与一键排障

## 更新内容

**新增**

- `vision_status` 诊断工具：一键查看版本、Ollama 连通性、模型就绪情况、可选依赖、缓存/重试配置
- 结果缓存：相同图片 + 相同参数自动命中缓存，第二次调用秒回
- Ollama 瞬时故障自动重试（429/5xx/网络抖动，指数退避）
- 返回内容带"不可信数据"前缀，防止图片内文字提示注入
- 输入校验：要求绝对路径 + 按文件真实内容校验格式
- 可选大图缩放：`LOCAL_VISION_MAX_DIMENSION`（默认关闭，防 detailed 卡死）
- PaddleOCR 初始化加锁，避免并发首次初始化互相踩缓存

## 快速上手

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

## 文档

- 部署与常见问题：https://github.com/Yuhang-uestc/deepvision-local-mcp/blob/master/docs/部署与常见问题.md
- 架构说明：https://github.com/Yuhang-uestc/deepvision-local-mcp/blob/master/docs/架构说明.md

## 许可

- 项目代码：MIT License
- 模型权重（yolov8*.pt 等）为 Ultralytics AGPL-3.0 许可，首次调用自动下载，不随仓库分发
