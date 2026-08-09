# Changelog

## v2.3.0（2026-08-09）

### 新增
- **多图支持**：`analyze_image(file_paths=[...])` 多图时逐张独立分析后合并返回（每张都完整看，带图1/图2…标签），不再只认第一张
- **`compare_images` 对比工具**：用户明确要求对比时，把多张图按图1/图2…编号拼成网格图，一次分析异同（工具数 11 → 12）

### 修复
- 多图输入静默丢弃第二张的问题（qwen3-vl 一次只认一张图，现改为逐张分析）
- EXIF 方向未处理：手机竖拍照片在分析/裁切/定位中会旋转 90°（现已自动转正）
- 非法颜色静默降级为红色：`cv_locate` / `draw_bounding_box` 传错颜色现在会明确报错
- `crop_image` 的 scale 无上限：放大后输出超过 50MP 会拒绝，防止内存被撑爆
- 裁切右/下边界被钳到 w-1：导致永远裁不到最后一行/列（现允许边界取到 w/h）
- 透明 PNG 在拼图/画框中变黑底（现以白色打底）
- `OLLAMA_HOST` 带路径（如代理地址 `https://host/api`）时端口会被追加到路径末尾，现只在 host:port 部分补端口
- PaddleOCR 结果解析器遇到畸形条目会整体抛异常，现逐条防御、跳过坏行

### 文档
- README / skill / 架构说明 / 开发记录同步多图策略与边界行为；新增 tests/test_edge_cases.py（22 项）与 tests/test_robustness.py（28 项）
- 注册与自检增强：`register-mcp.ps1` 自动写入 Python 绝对路径并升级旧注册；`check.ps1` 的 MCP 检查升级为真实握手探针（新增 `check_mcp.py`）；部署文档新增"MCP 工具没出现"排查
- 注册安全加固：`register-mcp.ps1` 改为调用 `register_mcp.py`（tomllib 外科手术式修改，只动 local_vision 一节；备份 + 写前/写后校验 + 失败自动回滚；检测运行中的 Codex 并中止）；文档与 README 增加"先退出 Codex 再注册"警告

## v2.2.0（2026-08-07）

### 新增
- `vision_status` 诊断工具：版本、Ollama 连通性、视觉模型就绪情况、可选依赖、缓存/重试配置
- `analyze_image` / `ocr_extract` 结果缓存：相同图片内容+参数命中缓存秒回（按内容哈希，可 `LOCAL_VISION_CACHE=0` 关闭）
- Ollama 瞬时故障自动重试（429/5xx/网络抖动，指数退避，默认 2 次；404 不重试）
- `analyze_image` / `ocr_extract` 返回带"不可信数据"安全前缀，防图片内文字提示注入
- PaddleOCR 初始化加锁串行化，避免并发首次初始化互相踩 `~/.paddlex` 缓存锁（Windows 上表现为 Permission denied）
- 输入校验：主要看图工具拒绝相对路径，并按文件真实内容（magic-byte）校验格式，错误更明确
- 可选大图缩放：`LOCAL_VISION_MAX_DIMENSION`（默认关闭），超长边大图发送前自动等比缩小，防 detailed 卡死
- `OLLAMA_HOST` 归一化：允许写裸主机/端口（如 `0.0.0.0`、`127.0.0.1:11434`），自动补全 `http://` 与默认端口，修复 "unknown url type" 报错
- 中文零样本自动本地翻译：`detect_by_text` 收到中文描述时，常见物体走词典直译、其余走本地 Ollama 翻译成英文再检测（`LOCAL_VISION_ZS_TRANSLATE=0` 关闭）
- 检测/分割自动降置信度重试（**默认关闭**）：结果为空且未显式指定 `min_confidence` 时，可设 `LOCAL_VISION_CONF_FLOOR=0.15` 开启自动按 0.25→0.15 降档重试；默认 `0` 保持原有稳定行为（降档会增加低置信度假目标，数人场景请谨慎）

### 修复
- `_format_detection_results` 兼容 `names` 为 list 的情况（YOLO-World `set_classes` 后触发），修复 `'list' object has no attribute 'get'` 崩溃
- 分割工具 `_class_name` 统一处理 `names` 为 list/dict 两种形态，消除同类崩溃隐患

### 文档
- README 新增"健壮性与安全"章节、环境变量表补 5 个新变量
- README 兼容性章节补充"各客户端粘贴图片落盘位置表"与"宿主 MCP 超时建议"
- 架构说明更新工具数（11 个）、工具表与关键设计决策
- 开发记录补同类项目调研心得与本次改动；部署手册补充 `PADDLE_PDX_CACHE_HOME` 缓存重定位、多账号场景与大图缩放说明
- 隐私表述修正：明确"图片文件与视觉识别在本机完成、原图不直接上传；识别文字随对话交给主模型（云端主模型可见）"，不再笼统宣称"全程不出机器/绝对隐私"

### 测试
- 离线测试新增：缓存命中、瞬时错误重试、不可信前缀、vision_status、相对路径拒绝、伪格式拒绝、可选缩放、names-list 兼容、中文词典直译

## v2.1.1（2026-08-07）

### 修复
- PaddleOCR 改用 `paddle_static` 引擎并禁用 HPI/oneDNN，规避 Paddle 3.x 的 `ConvertPirAttribute2RuntimeAttribute` bug（新增 `PADDLEOCR_KEEP_ONEDNN=1` 开关供用户自选保留）
- PaddleOCR 回退 Windows OCR 时在返回结果中附失败原因，不再静默
- 模型下载改为 GitHub 直连优先，curl 加 `--retry-all-errors` 断流自动续传

### 文档
- 新增用户向《部署与常见问题》、开发者《开发记录与踩坑》、《架构说明》
- README 增加特性、项目结构、文档入口
- skill 增加"大图优先 quick + 局部裁切"规则

## v2.1.0（2026-08-07）

### 新增
- `analyze_image` 快速/详细双模式（quick 默认 4B 自动回退 8B、上下文 4096、精简输出）
- `segment_objects` 像素级分割（掩膜 + 面积统计）
- `ocr_extract` 支持 PaddleOCR 可选引擎（auto/windows/paddle）
- YOLOE 零样本检测支持（含 mobileclip_blt.ts 后台下载与进度返回）
- YOLO-World 轻量零样本备选（约 25MB，无需 530MB 权重）
- `install-extra.ps1` 一键安装 PaddleOCR + CLIP

### 修复
- .ps1 脚本转 UTF-8 with BOM，修复 PowerShell 5.1 中文解析报错
- PaddleOCR 3.x 构造参数兼容

## v2.0.0（2026-08-06）

### 新增
- `crop_image` 裁切放大、`cv_locate` 颜色/模板定位、`detect_by_text` 零样本检测入口
- `draw_bounding_box` 支持一次多框（boxes 数组）、中文标签
- `analyze_image` 支持多图对比（file_paths）、温度参数
- `image_info` 工具
- 输出安全：`VISION_OUTPUT_DIR`、禁止覆盖输入图

## v1.0.0（2026-08-05）

### 新增
- 首个可用版本：`analyze_image` / `ocr_extract` / `draw_bounding_box` / `detect_objects` / `list_local_models`
- vision-perceive 多轮识图闭环 skill
- Windows 内置 OCR 桥接、YOLOv8 检测接入
- MCP 注册与 skill 安装脚本
