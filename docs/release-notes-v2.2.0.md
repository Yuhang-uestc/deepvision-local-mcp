给 DeepSeek 等纯文本模型补上本地"看图"能力：Ollama 视觉模型描述 + PaddleOCR 文字识别 + YOLO 检测/分割 + 零样本检测 + 颜色/模板定位 + 裁切放大，图片全程不出本机。

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
