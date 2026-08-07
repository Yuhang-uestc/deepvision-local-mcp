# Local Vision MCP（本地识图）

给纯文本主模型（DeepSeek 等）补上本地"看图"能力的 MCP server + 多轮识图闭环 skill。
**图片只在本机处理**：读取本地图片 → 本地 Ollama 视觉模型 / YOLO / PaddleOCR / OpenCV → 返回文字与坐标，全程不出机器。

![License](https://img.shields.io/badge/license-MIT-green.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-0078d6.svg)
![MCP](https://img.shields.io/badge/MCP-stdio-orange.svg)

## 特性

- 🖼️ **本地看图**：图片不出机器，隐私安全；DeepSeek 等纯文本模型也能"看图"
- 🔧 **专业工具分工**：视觉模型描述、PaddleOCR 场景文字识别（含坐标框）、YOLO 检测/分割、零样本检测、颜色/模板定位、裁切放大，各管一段
- 🔄 **多轮识图闭环**：概览 → 聚焦 → 文字 → 定位 → 放大 → 交叉校验 → 综合报告，过滤幻觉
- ⚡ **快慢双模式**：顺手附图走 quick（默认 4B、秒级返回），认真分析走 detailed（8B）
- 🧠 **健壮性**：相同图片+参数自动缓存（秒回）、Ollama 瞬时故障自动重试、图片内容按"不可信数据"处理（防提示注入）、`vision_status` 一键排障
- 🛡️ **部署友好**：server 零依赖起步；PaddleOCR / YOLOE 等重型能力可选、自动降级；下载支持断点续传与完整性校验
- 📦 **开箱脚本**：环境自检、MCP 注册、skill 安装、可选依赖一键装

## 为什么有这个东西

DeepSeek 等纯文本模型没有视觉能力，但通过 MCP 工具可以获得"看图"能力：由本地视觉模型负责"看"，主模型负责"想"。
本项目把看图拆成多个专业工具（描述、OCR、检测、定位、裁切放大），再用多轮闭环 skill 串起来，解决单次调用漏细节、位置说不准、幻觉等问题。

## 原理

![架构总览](examples/architecture.png)

一句话：**主模型负责"想"，本地引擎负责"看"，MCP 是桥，skill 是流程**；图片全程只在本机处理。

数据流：纯文本主模型（Codex / Claude Code / opencode / DeepSeek 等）→ `server.py`（MCP stdio，11 个工具）→
本地引擎（Ollama 视觉模型 / PaddleOCR / YOLO / OpenCV / Pillow）→ 返回文字与坐标 → 主模型交叉校验并输出最终报告。

## 文件

```
server.py                  MCP 服务器本体（单文件，基础零依赖）
win_ocr.ps1                Windows 内置 OCR 调用脚本
skills/vision-perceive/    多轮识图闭环 skill
tests/                     离线单元测试 + 真机冒烟测试
docs/                      架构说明 / 部署手册 / 开发记录
check.ps1                  环境自检
setup.ps1 / install.ps1 / install-extra.ps1 / register-mcp.ps1 / install-skill.ps1   安装与注册脚本
test_image.png             程序生成的合成测试图（不含任何真实信息）
LICENSE / CHANGELOG.md / CONTRIBUTING.md / requirements.txt
```

## 环境要求

- Python 3.9+
- [Ollama](https://ollama.com) 已安装并启动，视觉模型：`ollama pull qwen3-vl:8b`
- 可选：`python -m pip install -r requirements.txt`（Pillow / ultralytics / numpy）

## 安装（两种方式，任选其一）

> 安装完成后**重启 Codex** 即可使用。下方"工具/功能/排障"等章节均为参考材料，**安装阶段不必通读**。

### 方式一：一键安装（推荐）

```powershell
# 基础安装（描述 / 检测 / 分割 / OCR 兜底）
powershell -ExecutionPolicy Bypass -File setup.ps1

# 完整安装（+ PaddleOCR 场景文字 / YOLOE 零样本，需联网，体积较大）
powershell -ExecutionPolicy Bypass -File setup.ps1 -Extras
```

`setup.ps1` = 环境检查 +（可选依赖）+ 注册 MCP + 安装 skill 的整合脚本，可重复执行（幂等）。

### 方式二：分步安装（想看清每一步）

```powershell
# 0. 环境准备（一次性）
#    安装 Python 3.9+（https://www.python.org/downloads/）
#    安装并启动 Ollama（https://ollama.com）
ollama pull qwen3-vl:8b

# 1. 自检环境
powershell -ExecutionPolicy Bypass -File check.ps1

# 2.（可选）安装 PaddleOCR / CLIP（不装则 OCR 自动回退 Windows OCR）
powershell -ExecutionPolicy Bypass -File install-extra.ps1

# 3. 注册 MCP（只追加 local_vision，不会动你已有的 DeepSeek 配置）
powershell -ExecutionPolicy Bypass -File register-mcp.ps1

# 4. 安装识图 skill
powershell -ExecutionPolicy Bypass -File install-skill.ps1

# 5. 重启 Codex，然后说：分析这张图 C:/xxx/photo.png
```

## 工具

| 工具 | 用途 |
|---|---|
| `analyze_image` | 本地视觉模型分析图片；`mode=quick` 快速精简输出（默认 4B，自动回退）、`mode=detailed` 完整（默认 8B）；`file_paths` 可传多图（qwen3-vl 下仅首图生效，对比请分别分析单张）；`num_ctx`/`temperature` 可调 |
| `image_info` | 读取尺寸/格式/大小，确定坐标系 |
| `ocr_extract` | 文字提取；`engine=auto` 优先 PaddleOCR，否则 Windows OCR（含位置） |
| `detect_objects` | YOLO 检测 COCO 80 类，返回类别/置信度/坐标框；可 `save_path` 存标注图 |
| `segment_objects` | YOLO 分割（默认 yolov8n-seg.pt）：像素级掩膜 + 面积统计，遮挡数人/遥感量算用 |
| `detect_by_text` | YOLOE / YOLO-World 零样本检测：用文字描述找任意物体 |
| `cv_locate` | 颜色定位（mode=color）或模板匹配（mode=template） |
| `crop_image` | 裁切 + 放大局部区域，小字/小目标二次识别 |
| `draw_bounding_box` | 一次画多个框（boxes 数组），可视化验证 |
| `list_local_models` | 查看本机 Ollama 模型 |
| `vision_status` | 排障：版本、Ollama 连通性、模型就绪、可选依赖、缓存/重试配置 |

## 定位工具箱（该用哪个）

| 场景 | 工具 | 示例 |
|---|---|---|
| 数人、找常见物体 | `detect_objects` | `classes=["person"]` |
| 遮挡严重数人、面积量算 | `segment_objects` | `classes=["person"]`（掩膜更准） |
| 找任意物体 | `detect_by_text` | `text="消防栓, 蓝色帐篷"` |
| 找图例色块 | `cv_locate` | `mode="color", color="#3b6ea5"` |
| 找图标/logo | `cv_locate` | `mode="template", template_path=图标.png` |
| 小字/小目标 | `crop_image` | `scale=3` 后重新 OCR/分析 |
| 验证框准不准 | `draw_bounding_box` + `analyze_image` | 画框后让视觉模型确认 |

## 多轮识图闭环（vision-perceive skill）

收到图片分析请求时，按 skill 流程执行而不是单次调用：
概览 → 聚焦 → 文字提取 → 精确定位 → 局部放大 → 交叉校验 → 综合报告。
多轮一致的内容可信度高，单轮幻觉会被过滤；小字小目标强制先放大再识别。

## 目标检测依赖

```powershell
python -m pip install ultralytics
```

- `detect_objects` 默认 `yolov8n.pt`（首次自动下载约 6MB，可 `DETECTION_MODEL` 换 `yolov8s.pt` 等）
- `detect_by_text` 默认 `yoloe-v8s-seg.pt`（首次自动下载约 30MB），也可换 `yolov8s-world.pt`

`detect_by_text`（YOLOE）还需要 CLIP 文本编码依赖，否则会报 `No module named 'clip'`：

```powershell
python -m pip install git+https://github.com/ultralytics/CLIP.git
```

GitHub 不通时用镜像（任选其一）：

```powershell
python -m pip install git+https://ghproxy.net/https://github.com/ultralytics/CLIP.git
python -m pip install git+https://ghfast.top/https://github.com/ultralytics/CLIP.git
```

首次调用 YOLOE 还会联网下载 CLIP 权重（ViT-B/32，约 300MB）。

另外 YOLOE 的文本编码器需要 MobileCLIP 的 TorchScript 权重 `mobileclip_blt.ts`（约 530MB）。服务端会在首次调用
`detect_by_text` 时**后台**自动从镜像下载到项目目录（默认 ghproxy 镜像，可用环境变量 `MOBILECLIP_TS_URL` 更换）。
下载不阻塞调用：工具会立即返回进度，稍后重试即可继续。也可手动下载：

```powershell
curl -L -o mobileclip_blt.ts "https://ghproxy.net/https://github.com/ultralytics/assets/releases/download/v8.4.0/mobileclip_blt.ts"
```

ghproxy 对大文件可能中途截断；若失败，改用 GitHub 直连（release 资源通常可达）：

```powershell
curl.exe -L -C - -o mobileclip_blt.ts "https://github.com/ultralytics/assets/releases/download/v8.4.0/mobileclip_blt.ts"
```

**不想等 530MB 的话**：`detect_by_text` 可以立即改用 YOLO-World（约 25MB，文本编码内置，不需要 CLIP/mobileclip）。
调用时传 `model="yolov8s-world.pt"` 即可，权重缺失时服务端会自动后台从镜像下载。

可选依赖可一键安装：

```powershell
powershell -ExecutionPolicy Bypass -File install-extra.ps1
```

## 提速说明（顺手带图别再等几分钟）

- **快速模式**：`analyze_image(mode="quick")` 用 4B 模型（未安装自动回退 8B）、精简 prompt 控输出、上下文 4096，单次约 10~30 秒。skill 已规定：顺手附图只调一次 quick，不跑多轮。
- **详细模式**：`analyze_image(mode="detailed")` 用 8B 完整描述，仅在用户要求仔细分析时使用。
- **显存**：`num_ctx` 改小可省显存（8B 在 8GB 显存下会 20% 层跑 CPU，这是主要慢因）。
- 想更快：`ollama pull qwen3-vl:4b` 后快速模式自动使用。

提前下载零样本模型（可选，避免第一次调用等下载）：

```powershell
python -c "from ultralytics import YOLO; YOLO('yoloe-v8s-seg.pt')"
```

## 健壮性与安全（v2.2）

- **结果缓存**：`analyze_image` / `ocr_extract` 对"相同图片内容 + 相同参数"自动命中缓存（按内容哈希，文件被替换会自动失效），
  第二次调用秒回，不用重复等本地模型推理。可用 `LOCAL_VISION_CACHE=0` 关闭。
- **自动重试**：Ollama 瞬时故障（HTTP 429/5xx、网络抖动）自动指数退避重试（默认 2 次），模型不存在（404）不重试，直接给出安装提示。
- **不可信数据防护**：图片可能包含诱导性文字（如"忽略之前的指令"），因此 `analyze_image` / `ocr_extract` 的返回都带
  `[安全提示]` 前缀，提醒主模型把图片内容当数据、不当指令。
- **输入校验**：主要看图工具要求绝对路径，并按文件真实内容（magic-byte）校验格式，扩展名造假或传错文件会得到明确报错而非奇怪的解析错误。
- **可选大图缩放**：`LOCAL_VISION_MAX_DIMENSION`（默认关闭）可让超长边大图在发给 Ollama 前自动等比缩小，防止 detailed 模式卡死；
  注意整图缩放会损失全局细节——需要精度的场景仍然先用 `crop_image` 裁出目标区域放大，那个路径不受影响。
- **一键排障**：`vision_status` 输出版本、Ollama 连通性、两个视觉模型是否已安装、可选依赖状态、缓存/重试配置，
  遇到"连不上 / 没模型 / 缺依赖"先调它。

## 测试

```powershell
python tests\test_server.py
```

离线测试用 mock Ollama 验证协议与全部工具，共 21 项（analyze / 缓存命中 / 瞬时错误重试 / 相对路径拒绝 / 伪格式拒绝 / 可选大图缩放 / crop / draw / cv_locate / 错误路径 / 输出目录限制）。

## 开源与许可

- 本项目代码：MIT License。
- **模型权重不随仓库分发**：yolov8n.pt / yoloe-*.pt 等为 AGPL-3.0 许可（Ultralytics），首次调用自动下载，用户自担许可责任。
- **绝不提交**：`config.toml`（含 DeepSeek API Key）、`*.bak-*`、`.cache/`、真人照片测试图（`.gitignore` 已屏蔽）。
- 图片仅发往本机 Ollama（默认 `http://localhost:11434`），不上传任何云端。

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama 服务地址 |
| `OLLAMA_VISION_MODEL` | `qwen3-vl:8b` | 默认视觉模型 |
| `VISION_MODEL_QUICK` | `qwen3-vl:4b` | 快速模式模型（未安装自动回退 8B） |
| `LOCAL_VISION_MAX_MB` | `20` | 单张图片大小上限（MB） |
| `LOCAL_VISION_CACHE` | `1` | 结果缓存开关（相同图片+参数秒回），`0` 关闭 |
| `LOCAL_VISION_CACHE_TTL` | `1800` | 缓存有效期（秒） |
| `LOCAL_VISION_CACHE_MAX` | `64` | 缓存最大条数（超出淘汰最旧） |
| `LOCAL_VISION_RETRIES` | `2` | Ollama 瞬时故障（429/5xx/网络抖动）重试次数 |
| `LOCAL_VISION_RETRY_BASE` | `2.0` | 重试退避基数（秒，第 n 次等待 `基数×2^(n-1)`） |
| `LOCAL_VISION_MAX_DIMENSION` | `0`（关闭） | 可选。`analyze_image` 发送给 Ollama 前的最大边长（px），超限大图自动等比缩小，防 detailed 卡死；全局细节会略降，要精度请用 `crop_image` 局部裁切 |
| `DETECTION_MODEL` | `yolov8n.pt` | 默认 COCO 检测模型 |
| `SEGMENTATION_MODEL` | `yolov8n-seg.pt` | 默认分割模型 |
| `DETECTION_TEXT_MODEL` | `yoloe-v8s-seg.pt` | 默认零样本检测模型 |
| `VISION_OUTPUT_DIR` | 项目 `outputs/` | 设置后强制所有生成文件写入该目录 |
| `PADDLEOCR_KEEP_ONEDNN` | 空 | 设为 `1` 保留 PaddleOCR 的 oneDNN（需 paddle 版本无 bug 或 GPU 版，见部署手册） |

## 部署与排障

- [架构说明](docs/架构说明.md) — 设计目标、分层、数据流、设计决策、扩展点
- [部署与常见问题（用户向）](docs/部署与常见问题.md) — 照做即可部署，按症状查问题
- [开发记录与踩坑（内部）](docs/开发记录与踩坑.md) — 开发过程所有问题的根因与对策

## 已知限制

- **qwen3-vl:8b 定位能力弱**：能验证框、描述场景、读文字，但直接输出精确坐标不可靠——因此定位交给 YOLO/OpenCV。
- **qwen3-vl 设置 num_predict（max_tokens）会返回空输出**（实测 Ollama 行为），所以限长靠精简 prompt 而不是参数。
- **多图对比（file_paths）在 qwen3-vl:8b 下实测无效**：Ollama 只把第一张图传给模型，第二张会被忽略；需要对比时改为分别分析单张图，由主模型综合。
- **OCR 有误读率**：系统 OCR 偶发识别错误，重要文字建议与视觉模型交叉核对；艺术字/手写效果差。
- **OCR 坐标在 PowerShell 5.1 下为 0**：仅指 Windows 内置 OCR 兜底路径（WinRT 限制）；使用 PaddleOCR 引擎时坐标正常。安装 [PowerShell 7](https://github.com/PowerShell/PowerShell) 后兜底路径的坐标也可用。
- **8B 模型速度**：每次识图约 20~60 秒，可换 4B 提速。
- **模板匹配对纯色模板失效**：请裁取含纹理/边缘的区域作为模板。

## 兼容性（换工具 / 换模型 / 换平台）

本项目按标准 MCP 协议设计，**视觉能力与主模型、客户端解耦**。当前已验证组合：**Codex + DeepSeek（Windows）**；
以下组合按标准协议兼容，**未逐项实测**，遇到问题按"部署与常见问题"排查。

### 1. 换主模型（脑）

server.py 不依赖 DeepSeek，只认 MCP 协议。只要你的客户端支持 MCP 工具调用，任何主流模型
（Claude、GPT、Qwen、GLM、Kimi 等）都能作为"脑"使用——在客户端里切换模型即可，本项目无需改动。
工具描述为中文，主流模型均可正确读取。

### 2. 换客户端（工具）

把 server.py 注册成标准 MCP stdio 服务即可：

```json
{
  "mcpServers": {
    "local_vision": {
      "command": "python",
      "args": ["C:/绝对路径/server.py"]
    }
  }
}
```

> 提示：如果用了 conda/venv，建议把 `command` 写成该环境的 Python 绝对路径（如 `E:/miniconda3/python.exe`），
> 避免客户端进程没有继承虚拟环境 PATH 时找到错误解释器。

| 客户端 | 注册方式 | 说明 |
|---|---|---|
| Codex | `register-mcp.ps1` / `setup.ps1` | 已自动化，含 skill 安装 |
| Claude Code | 项目根目录 `.mcp.json`，或 `claude mcp add` | 同样支持 Agent Skills（SKILL.md） |
| Cursor | 设置 → MCP → 添加（写入 `~/.cursor/mcp.json`）或项目 `.cursor/mcp.json` | 无原生 skills，可用 rules 引用多轮流程 |
| Trae | 设置 → MCP → 创建 → 手动配置（stdin 类型） | 同上 |
| opencode / Windsurf / Cline / JetBrains / Cherry Studio 等 | 各自 MCP 设置界面，填入同一段配置 | MCP 生态通用 |

#### 换客户端后的常见坑

**粘贴的图片去哪了？** 各客户端把粘贴图片落盘的位置不同，`analyze_image` 需要的是图片路径：

| 客户端 | 粘贴图片落盘位置 |
|---|---|
| Codex | `~/.codex/attachments/<会话>/image-*.png` |
| Claude Code | `~/.claude/image-cache/<uuid>/N.png`（Alt+V 粘贴） |
| opencode | `~/.local/share/opencode/opencode.db`（SQLite，需 Node ≥22.5 提取） |
| Cursor / Trae / 其他桌面端 | 各自的附件/上传目录（不通用，优先把图片文件直接拖进对话框拿路径） |

**Windows 剪贴板的坑**：在资源管理器里对图片"复制"（Ctrl+C）复制的是**文件路径列表**而不是图片内容，
在 CLI 客户端里直接粘贴不一定生效；把图片文件**拖进对话框**（插入路径）最稳。

**宿主超时建议**：本地视觉推理比纯文本慢（4B 约 10~30s、8B 约 20~60s），部分宿主默认 MCP 超时只有 30~60 秒，
首次调用或大图时可能被宿主掐断。建议把该 MCP 服务的超时调到 120000ms 以上（Codex 对应 `startup_timeout_sec`，
其他客户端在 MCP 配置里找 timeout/timeoutMs 字段）。

### 3. 换视觉模型（眼）

Ollama 上任意视觉模型都可用：

```powershell
ollama pull qwen3-vl:4b        # 快速模式（更小更快）
ollama pull llava:13b          # 或 llava / gemma3-v 等其他视觉模型
```

通过环境变量或调用参数切换：`OLLAMA_VISION_MODEL`（detailed）、`VISION_MODEL_QUICK`（quick）、或 `analyze_image` 的 `model` 参数。

### 4. skill 移植（可选）

- **Codex**：`install-skill.ps1` 一键安装
- **Claude Code**：skill 就是标准 `SKILL.md`（YAML frontmatter + Markdown），直接复制 `skills/vision-perceive` 到项目 `.claude/skills/` 或 `~/.claude/skills/` 即可，格式天然兼容
- **Cursor / Trae 等**：没有原生 skills，但 MCP 工具本身可用；把 `SKILL.md` 里的"模式决策 + 多轮流程"复制进 rules/自定义指令即可获得同等闭环效果

### 5. 平台说明

- **Windows**：完整测试路径（含 Windows 内置 OCR 兜底）
- **Linux / macOS**：server.py、Ollama、ultralytics、PaddleOCR 均跨平台可用；但 `win_ocr.ps1`（Windows OCR 兜底）不可用，OCR 需依赖 PaddleOCR（跨平台），或自行接入 tesseract 等
- `.ps1` 安装脚本仅 Windows；其他平台按上面的 MCP 配置 JSON 手动注册即可

### 明确不兼容 / 注意

- `file_paths` 多图对比在 qwen3-vl 下实测只认第一张图（与客户端无关，是模型行为）
- 坐标类任务请走检测/分割工具，别指望任何视觉模型直接报坐标

## 常见问题

- **连不上 Ollama**：确认系统托盘有 Ollama 图标，或命令行先跑 `ollama list`。
- **报"模型不存在"**：先 `ollama pull qwen3-vl:8b`。
- **检测报"需要联网下载权重"**：首次使用需联网下载模型权重，网络通后重试。
- **改了代码没生效**：重启 Codex（工具列表是启动时加载的）。
