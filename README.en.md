# Local Vision MCP

English | [简体中文](README.md)

An MCP server + multi-round vision skill that gives pure-text LLMs (DeepSeek, etc.) local "sight".
**Images and vision processing never leave your machine**: read a local image → local Ollama vision model / YOLO / PaddleOCR / OpenCV → return text and coordinates. Raw images are not uploaded directly.
Recognized text does enter the main model's conversation — if your main model is a cloud API (e.g., DeepSeek), that text is sent to its servers. For full isolation, pair it with a local main model.

![License](https://img.shields.io/badge/license-MIT-green.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-0078d6.svg)
![MCP](https://img.shields.io/badge/MCP-stdio-orange.svg)

## Features

- 🖼️ **Local vision**: image files and vision processing stay on your machine; raw images are never uploaded. Recognized text goes to the main model with your conversation (visible to a cloud main model)
- 🔧 **Specialized tools**: vision-model description, PaddleOCR scene text recognition (with boxes), YOLO detection/segmentation, zero-shot detection, color/template locating, and crop-and-zoom — each handles one job
- 🔄 **Multi-round vision loop**: overview → focus → text → locate → zoom → cross-check → final report, to filter hallucinations
- ⚡ **Quick & detailed modes**: quick (default 4B, returns in seconds) for casual attachments; detailed (8B) for careful analysis
- 🧠 **Robustness**: content-based caching for identical image+params (instant repeat), automatic retry on transient Ollama errors, image content treated as "untrusted data" (prompt-injection guard), and a `vision_status` diagnostic tool
- 🛡️ **Deployment friendly**: zero-dependency server core; heavy optional features (PaddleOCR / YOLOE) degrade gracefully; downloads support resume and integrity checks
- 📦 **One-click scripts**: environment check, MCP registration, skill install, optional dependencies

## Demo

Real tool output on the same dashboard screenshot: `cv_locate` color locating (green/red card strips) + PaddleOCR text recognition (with boxes) + local qwen3-vl analysis (image processed locally):

![Real tool output demo](examples/demo_annotated.png)

## Why this exists

Pure-text models like DeepSeek have no vision, but via MCP tools they can "see": a local vision model does the seeing, and the main model does the thinking.
This project splits "seeing" into specialized tools (description, OCR, detection, locating, crop-and-zoom) and orchestrates them with a multi-round skill to avoid missed details, vague positions, and hallucinations from single calls.

## How it works

![Architecture overview](examples/architecture.png)

In one line: **the main model thinks, local engines see, MCP is the bridge, and the skill is the process**; images and vision processing stay local.

Data flow: pure-text main model (Codex / Claude Code / opencode / DeepSeek, etc.) → `server.py` (MCP stdio, 11 tools) → local engines (Ollama vision model / PaddleOCR / YOLO / OpenCV / Pillow) → text and coordinates → main model cross-checks and produces the final answer.

## Files

```
server.py                  MCP server (single file, zero-dependency core)
call_tool.py               command-line tool access (CLI fallback when MCP is unavailable)
register_mcp.py            safe MCP registration in Python
check_mcp.py               MCP connectivity handshake probe
win_ocr.ps1                Windows built-in OCR bridge
skills/vision-perceive/    multi-round vision skill
tests/                     offline unit tests + real-machine smoke tests
docs/                      architecture / deployment / dev notes
check.ps1                  environment check
setup.ps1 / install.ps1 / install-extra.ps1 / register-mcp.ps1 / install-skill.ps1   install & registration scripts
examples/                  synthetic sample images and showcase images
benchmarks/                reproducible benchmarks (synthetic cases + metric reports, see "Tests")
LICENSE / CHANGELOG.md / CONTRIBUTING.md / requirements.txt
```

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com) installed and running; vision model: `ollama pull qwen3-vl:8b`
- Optional: `python -m pip install -r requirements.txt` (Pillow / ultralytics / numpy)

## Installation (either way)

> **Restart Codex after installation.** The sections below (tools/features/troubleshooting) are reference material — you do not need to read them before installing.

### Option 1: One-click install (recommended)

```powershell
# Basic install (description / detection / segmentation / OCR fallback)
powershell -ExecutionPolicy Bypass -File setup.ps1

# Full install (+ PaddleOCR scene text / YOLOE zero-shot; needs network, larger)
powershell -ExecutionPolicy Bypass -File setup.ps1 -Extras
```

`setup.ps1` = environment check + (optional deps) + MCP registration + skill install in one idempotent script.

### Option 2: Step by step

```powershell
# 0. Environment (once)
#    Install Python 3.9+ (https://www.python.org/downloads/)
#    Install and start Ollama (https://ollama.com)
ollama pull qwen3-vl:8b

# 1. Check environment
powershell -ExecutionPolicy Bypass -File check.ps1

# 2. (Optional) Install PaddleOCR / CLIP (OCR falls back to Windows OCR if skipped)
powershell -ExecutionPolicy Bypass -File install-extra.ps1

# 3. Register MCP (only appends local_vision; won't touch your existing DeepSeek config)
powershell -ExecutionPolicy Bypass -File register-mcp.ps1

# 4. Install the vision skill
powershell -ExecutionPolicy Bypass -File install-skill.ps1

# 5. Restart Codex, then say: analyze this image C:/xxx/photo.png
```

## Tools

| Tool | Purpose |
|---|---|
| `analyze_image` | Local vision model analyzes an image; `mode=quick` for a short fast result (default 4B, auto-fallback), `mode=detailed` for a full one (default 8B); `file_paths` analyzes multiple images one by one and merges the results (every image is fully seen); `num_ctx` / `temperature` adjustable |
| `compare_images` | Use when the user explicitly asks to compare: images are merged into a labeled grid (图1/图2…) and analyzed in one pass (images are downscaled; for details, analyze each image separately with `analyze_image`) |
| `image_info` | Read dimensions / format / size to establish the coordinate system |
| `ocr_extract` | Text extraction; `engine=auto` prefers PaddleOCR, otherwise Windows OCR (with positions) |
| `detect_objects` | YOLO detection over COCO 80 classes; returns class/confidence/box; `save_path` saves an annotated image |
| `segment_objects` | YOLO segmentation (default yolov8n-seg.pt): pixel-level masks + area stats; for occluded counting / area measurement |
| `detect_by_text` | YOLOE / YOLO-World zero-shot detection: find arbitrary objects from a text description |
| `cv_locate` | Color locating (`mode=color`) or template matching (`mode=template`) |
| `crop_image` | Crop and zoom into a region for a second pass on small text/objects |
| `draw_bounding_box` | Draw multiple boxes at once (`boxes` array) for visual verification |
| `list_local_models` | List local Ollama models |
| `vision_status` | Troubleshooting: version, Ollama reachability, model readiness, optional deps, cache/retry config |

## Use directly from the command line (CLI fallback)

If your client does not inject the MCP tools into the current conversation (you don't see `analyze_image` / `ocr_extract` etc.),
you can call the same local tools from the command line — results are identical to the MCP tools:

```powershell
python call_tool.py <tool> '<JSON args>'
```

Examples:

- Describe an image: `python call_tool.py analyze_image '{"file_path":"C:/x.png","mode":"quick"}'`
- Extract text: `python call_tool.py ocr_extract '{"file_path":"C:/x.png","engine":"auto"}'`
- Count/find objects: `python call_tool.py detect_objects '{"file_path":"C:/x.png","classes":["person"]}'`

Running it without arguments lists all 12 tools. The `vision-perceive` skill includes this fallback: when MCP tools are
unavailable it automatically switches to the CLI, so vision analysis never gets skipped because the client didn't inject tools.

## Which locating tool should I use?

| Scenario | Tool | Example |
|---|---|---|
| Count people / find common objects | `detect_objects` | `classes=["person"]` |
| Count people with heavy occlusion / area measurement | `segment_objects` | `classes=["person"]` (masks are more accurate) |
| Find arbitrary objects | `detect_by_text` | `text="fire hydrant, blue tent"` |
| Find legend color blocks | `cv_locate` | `mode="color", color="#3b6ea5"` |
| Find icons/logos | `cv_locate` | `mode="template", template_path=icon.png` |
| Small text / small objects | `crop_image` | `scale=3` then OCR/analyze again |
| Verify boxes | `draw_bounding_box` + `analyze_image` | draw, then ask the vision model to confirm |

Chinese descriptions are automatically translated to English before detection (common objects via a built-in dictionary, others via local Ollama; disable with `LOCAL_VISION_ZS_TRANSLATE=0`).

## Multi-round vision loop (vision-perceive skill)

When an image analysis request comes in, follow the skill flow instead of a single call: overview → focus → text extraction → precise locating → local zoom → cross-check → final report.
Multi-round consistent content is trusted; single-round hallucinations get filtered out. Small text/objects are zoomed first, then recognized.

**How to invoke**
- Explicitly: type `@vision-perceive` before an image request (e.g. `@vision-perceive analyze this image`) to force this flow;
- Automatically: in a new conversation with this directory as the workspace, [AGENTS.md](AGENTS.md) injects the vision rules (including the CLI fallback) — no prefix needed.

## Detection dependencies

```powershell
python -m pip install ultralytics
```

- `detect_objects` defaults to `yolov8n.pt` (auto-downloaded on first use, ~6MB; switch via `DETECTION_MODEL` to e.g. `yolov8s.pt`)
- `detect_by_text` defaults to `yoloe-v8s-seg.pt` (~30MB auto-download), or use `yolov8s-world.pt`

`detect_by_text` (YOLOE) also needs the CLIP text encoder, otherwise you get `No module named 'clip'`:

```powershell
python -m pip install git+https://github.com/ultralytics/CLIP.git
```

If GitHub is unreachable, use a mirror (pick one):

```powershell
python -m pip install git+https://ghproxy.net/https://github.com/ultralytics/CLIP.git
python -m pip install git+https://ghfast.top/https://github.com/ultralytics/CLIP.git
```

The first YOLOE call also downloads the CLIP weights (ViT-B/32, ~300MB) from the network.

YOLOE's text encoder additionally needs MobileCLIP TorchScript weights `mobileclip_blt.ts` (~530MB). The server downloads it **in the background** from mirrors on the first `detect_by_text` call (default mirror ghproxy; change via `MOBILECLIP_TS_URL`).
The download does not block the call: the tool returns progress immediately, and you retry shortly after. Manual download:

```powershell
curl -L -o mobileclip_blt.ts "https://ghproxy.net/https://github.com/ultralytics/assets/releases/download/v8.4.0/mobileclip_blt.ts"
```

ghproxy may truncate large files; if so, use direct GitHub (release assets are usually reachable):

```powershell
curl.exe -L -C - -o mobileclip_blt.ts "https://github.com/ultralytics/assets/releases/download/v8.4.0/mobileclip_blt.ts"
```

**Don't want to wait for the 530MB file?** `detect_by_text` can immediately use YOLO-World (~25MB, text encoder built in, no CLIP/mobileclip needed). Pass `model="yolov8s-world.pt"`; the server auto-downloads it in the background if missing.

Optional dependencies can be installed with one command:

```powershell
powershell -ExecutionPolicy Bypass -File install-extra.ps1
```

## Speed tips (stop waiting minutes for a casual attachment)

- **Quick mode**: `analyze_image(mode="quick")` uses the 4B model (auto-fallback to 8B if not installed), a compact prompt, and context 4096 — ~10-30s per call. The skill already mandates: one quick call for casual attachments, no multi-round loops.
- **Detailed mode**: `analyze_image(mode="detailed")` uses 8B for a full description; only when the user asks for careful analysis.
- **VRAM**: lowering `num_ctx` saves VRAM (8B on 8GB VRAM runs ~20% of layers on CPU, the main cause of slowness).
- Faster: `ollama pull qwen3-vl:4b`, then quick mode uses it automatically.

Pre-download the zero-shot model (optional, avoids waiting on first call):

```powershell
python -c "from ultralytics import YOLO; YOLO('yoloe-v8s-seg.pt')"
```

## Robustness & security (v2.2)

- **Result caching**: `analyze_image` / `ocr_extract` cache by "same image content + same params" (content hash, so replacing a file invalidates the cache). Repeat calls return instantly. Disable with `LOCAL_VISION_CACHE=0`.
- **Auto retry**: transient Ollama failures (HTTP 429/5xx, network jitter) retry with exponential backoff (default 2); a missing model (404) is not retried — you get an install hint instead.
- **Untrusted-data guard**: images may contain adversarial text (e.g., "ignore previous instructions"), so `analyze_image` / `ocr_extract` results carry a `[安全提示]` prefix, reminding the main model to treat image content as data, not instructions.
- **Input validation**: main image tools require absolute paths and validate the real format by magic bytes; mismatched or fake files produce a clear error instead of a weird parse failure.
- **Optional large-image downscale**: `LOCAL_VISION_MAX_DIMENSION` (off by default) can shrink oversized images before sending to Ollama to prevent detailed-mode hangs. Note that whole-image scaling loses global detail — for precision, crop the target region with `crop_image` first (that path is unaffected).
- **One-command troubleshooting**: `vision_status` prints version, Ollama reachability, whether both vision models are installed, optional dependency status, and cache/retry config. Call it first for "can't connect / no model / missing deps".

## Tests

```powershell
python tests\test_server.py
python tests\test_edge_cases.py
python tests\test_robustness.py
python tests\test_cli.py
```

Offline tests verify the protocol and all tools with a mocked Ollama: 98 checks — `test_server.py` (37: analyze / cache / transient retry incl. 429 / per-image multi-image / montage comparison / relative-path rejection / fake-format rejection / oversized-image rejection / crop / draw / cv_locate / error paths / output-dir enforcement / zero-shot translation bridge), `test_edge_cases.py` (22: EXIF orientation / transparent white background / invalid-color errors / crop scale memory cap / reversed boxes / format compatibility / locating edge cases), `test_robustness.py` (28: cache TTL/eviction/concurrency / Ollama host normalization / defensive Paddle parsing / detection formatting / montage extremes / tool schemas / output-overwrite protection / benchmark utilities), and `test_cli.py` (11: CLI fallback — usage / unknown tool / bad JSON / direct args / args-file / stdin / exit codes).

There is also a **reproducible benchmark** (quantified accuracy, synthetic images + ground truth):

```powershell
python benchmarks\generate_cases.py
python benchmarks\run_benchmark.py
```

It covers OCR (Chinese/English/tables/small text), color locating & counting, template matching, crop, and input validation; reports go to `benchmarks\report\`. Metric definitions and the custom detection dataset format are in `benchmarks\README.md` (Chinese).

## Open source & license

- Project code: MIT License.
- **Model weights are not distributed with the repo**: yolov8n.pt / yoloe-*.pt etc. are AGPL-3.0 (Ultralytics); auto-downloaded on first use, users are responsible for license compliance.
- **Never committed**: `config.toml` (contains your DeepSeek API key), `*.bak-*`, `.cache/`, real-person test photos (blocked by `.gitignore`).
- Images are processed locally only (local Ollama / PaddleOCR / YOLO / OpenCV) and never uploaded directly; conversation content (including recognized text) follows your main model's policy.

## Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama address; bare host/port accepted (e.g. `0.0.0.0`, `127.0.0.1:11434`), protocol/port auto-completed |
| `OLLAMA_VISION_MODEL` | `qwen3-vl:8b` | Default vision model |
| `VISION_MODEL_QUICK` | `qwen3-vl:4b` | Quick-mode model (auto-fallback to 8B if not installed) |
| `LOCAL_VISION_MAX_MB` | `20` | Max single image size (MB) |
| `LOCAL_VISION_CACHE` | `1` | Result cache toggle (identical image+params return instantly); `0` disables |
| `LOCAL_VISION_CACHE_TTL` | `1800` | Cache TTL (seconds) |
| `LOCAL_VISION_CACHE_MAX` | `64` | Max cache entries (oldest evicted) |
| `LOCAL_VISION_RETRIES` | `2` | Retry count for transient Ollama failures (429/5xx/network jitter) |
| `LOCAL_VISION_RETRY_BASE` | `2.0` | Backoff base (seconds; nth wait = `base×2^(n-1)`) |
| `LOCAL_VISION_MAX_DIMENSION` | `0` (off) | Optional. Max edge (px) before sending to Ollama; oversized images shrink proportionally to prevent detailed-mode hangs; global detail decreases — for precision use `crop_image` |
| `LOCAL_VISION_ZS_TRANSLATE` | `1` | Local Chinese→English translation for `detect_by_text` (dictionary + Ollama fallback); `0` disables |
| `LOCAL_VISION_CONF_FLOOR` | `0` (off) | Optional. Set e.g. `0.15` to enable "auto-lower confidence and retry when no results" (fewer misses, but possible low-confidence false positives; be careful when counting people); off by default for stability |
| `DETECTION_MODEL` | `yolov8n.pt` | Default COCO detection model |
| `SEGMENTATION_MODEL` | `yolov8n-seg.pt` | Default segmentation model |
| `DETECTION_TEXT_MODEL` | `yoloe-v8s-seg.pt` | Default zero-shot detection model |
| `VISION_OUTPUT_DIR` | project `outputs/` | Forces all generated files into this directory when set |
| `PADDLEOCR_KEEP_ONEDNN` | empty | Set to `1` to keep PaddleOCR's oneDNN (only if your paddle version has no bug or you use the GPU build; see deployment docs) |

## Deployment & troubleshooting

- [Architecture](docs/架构说明.md) — goals, layers, data flow, design decisions, extension points (Chinese)
- [Deployment & FAQ (user-facing)](docs/部署与常见问题.md) — follow it step by step; look up symptoms (Chinese)
- [Dev notes & pitfalls (internal)](docs/开发记录与踩坑.md) — root causes and fixes for every issue encountered (Chinese)

## Known limitations

- **qwen3-vl:8b localization is weak**: it can verify boxes, describe scenes, and read text, but direct pixel coordinates are unreliable — so locating is delegated to YOLO/OpenCV.
- **Recognized text goes to the cloud with your conversation**: image files never leave the machine, but OCR/description text enters the main model's conversation; with a cloud API main model (e.g., DeepSeek), that text is sent to its servers. Pair with a local main model (e.g., qwen3 / deepseek-r1 in Ollama) for full isolation.
- **Zero-shot Chinese descriptions rely on local translation**: common objects use a dictionary; the rest use local Ollama (a few seconds). If Ollama is down, only dictionary terms work — use English for complex descriptions.
- **qwen3-vl returns empty output when `num_predict` (max_tokens) is set** (verified Ollama behavior); keep output length controlled with a compact prompt instead.
- **Multi-image strategy**: qwen3-vl only reads one image per call, so `analyze_image(file_paths=[...])` analyzes each image separately and merges the results (every image is fully seen). When the user explicitly asks to "compare/differences", use `compare_images` (grid montage). The montage downscales images; for details, analyze each image separately.
- **OCR has a misread rate**: occasional errors; cross-check important text with the vision model. Artistic fonts/handwriting work poorly.
- **OCR coordinates are 0 under PowerShell 5.1**: only for the Windows built-in OCR fallback path (WinRT limitation); coordinates are normal with the PaddleOCR engine. Installing [PowerShell 7](https://github.com/PowerShell/PowerShell) fixes the fallback path too.
- **8B model speed**: ~20-60s per image; use 4B for speed.
- **Template matching fails on solid-color templates**: crop a region containing texture/edges as the template.
- **PaddleOCR may silently fall back to Windows OCR**: in `auto` mode, if PaddleOCR fails to initialize (most commonly the process lacks write permission to `%USERPROFILE%\.paddlex`, e.g. sandbox / restricted environments / some antivirus), it falls back to the system OCR and notes "已回退 Windows OCR" in the result — this is not a failure; recognition still works, just slightly less accurate and more prone to Chinese table misreads. To force PaddleOCR, pass `engine="paddle"` explicitly (init failures then surface as errors). Running in a normal terminal rarely triggers the fallback.

## Compatibility (switching tools / models / platforms)

This project follows the standard MCP protocol — **vision is decoupled from the main model and the client**. The verified combination is **Codex + DeepSeek (Windows)**; the combinations below are compatible by protocol but **not individually tested**. If something goes wrong, follow "Deployment & FAQ".

Important premise: **whether MCP tools are actually callable depends on the client injecting them into the current conversation** — this is client behavior, not a property of the server (e.g. some desktop clients do not inject MCP tools for third-party model channels; the client's own bundled MCP servers may not be injected either). Therefore:

- When the client supports MCP tool calls, this project works directly;
- When the client does not inject MCP tools, the **CLI fallback still works**: `python call_tool.py <tool> '<JSON args>'`, fully equivalent to the MCP tools (see "Use directly from the command line");
- For scenario-based tool selection, see [docs/识图使用指南.md](docs/识图使用指南.md) (Chinese).

### 1. Switch the main model (the brain)

server.py does not depend on DeepSeek; it only speaks MCP. Any mainstream model (Claude, GPT, Qwen, GLM, Kimi, etc.) can be the "brain" as long as your client supports MCP tool calls — just switch the model in your client; no changes to this project. Tool descriptions are in Chinese; mainstream models read them fine.

### 2. Switch the client (the tool)

Register server.py as a standard MCP stdio server:

```json
{
  "mcpServers": {
    "local_vision": {
      "command": "python",
      "args": ["C:/absolute/path/server.py"]
    }
  }
}
```

> Tip: `register-mcp.ps1` already writes the current environment's Python absolute path. If configuring manually, set `command` to that environment's Python absolute path (e.g. `E:/miniconda3/python.exe`) so the client doesn't pick the wrong interpreter (e.g. the Microsoft Store stub) when it lacks the venv PATH.

| Client | Registration | Notes |
|---|---|---|
| Codex | `register-mcp.ps1` / `setup.ps1` | Automated; includes skill install |
| Claude Code | project-root `.mcp.json`, or `claude mcp add` | Agent Skills (SKILL.md) supported |
| Cursor | Settings → MCP → Add (write `~/.cursor/mcp.json`) or project `.cursor/mcp.json` | No native skills; reference the multi-round flow via rules |
| Trae | Settings → MCP → Create → manual config (stdin type) | Same as above |
| opencode / Windsurf / Cline / JetBrains / Cherry Studio etc. | their own MCP settings UI, paste the same config | Generic MCP ecosystem |

#### Common pitfalls after switching clients

**Where did my pasted image go?** Each client stores pasted images in a different location; `analyze_image` needs a path:

| Client | Pasted image location |
|---|---|
| Codex | `~/.codex/attachments/<session>/image-*.png` |
| Claude Code | `~/.claude/image-cache/<uuid>/N.png` (Alt+V paste) |
| opencode | `~/.local/share/opencode/opencode.db` (SQLite; extract with Node ≥22.5) |
| Cursor / Trae / other desktop apps | their own attachment/upload dirs (not standardized; prefer dragging the image file into the dialog to get a path) |

**Windows clipboard pitfall**: "Copying" an image in Explorer (Ctrl+C) copies a **file path list**, not image content — pasting it directly in a CLI client may not work. Dragging the image file **into the dialog** (which inserts a path) is the most reliable.

**Host timeout**: local vision inference is slower than text (4B ~10-30s, 8B ~20-60s). Some hosts default MCP timeout to 30-60s and may kill the first call or large images. Raise this MCP server's timeout to 120000ms or more (Codex: `startup_timeout_sec`; other clients: a timeout/timeoutMs field in the MCP config).

### 3. Switch the vision model (the eyes)

Any Ollama vision model works:

```powershell
ollama pull qwen3-vl:4b        # quick mode (smaller, faster)
ollama pull llava:13b          # or llava / gemma3-v / other vision models
```

Switch via env vars or call params: `OLLAMA_VISION_MODEL` (detailed), `VISION_MODEL_QUICK` (quick), or `analyze_image`'s `model` parameter.

### 4. Porting the skill (optional)

- **Codex**: `install-skill.ps1` one-click install
- **Claude Code**: a skill is a standard `SKILL.md` (YAML frontmatter + Markdown); copy `skills/vision-perceive` to the project `.claude/skills/` or `~/.claude/skills/` — format is natively compatible
- **Cursor / Trae etc.**: no native skills, but the MCP tools work; copy the "mode decision + multi-round flow" from `SKILL.md` into rules/custom instructions to get the same loop

### 5. Platform notes

- **Windows**: fully tested (including the Windows OCR fallback)
- **Linux / macOS**: server.py, Ollama, ultralytics, and PaddleOCR are cross-platform; but `win_ocr.ps1` (Windows OCR fallback) is unavailable — OCR needs PaddleOCR (cross-platform) or another engine like tesseract
- `.ps1` install scripts are Windows-only; other platforms register manually with the MCP config JSON above

### Explicitly incompatible / notes

- `file_paths` analyzes multiple images one by one and merges results; "comparison" uses `compare_images` (montage, images are downscaled)
- Coordinate tasks should use detection/segmentation tools; don't expect any vision model to output precise coordinates directly

## FAQ

- **Can't reach Ollama**: confirm the Ollama tray icon is running, or run `ollama list` in a terminal first.
- **"Model not found"**: run `ollama pull qwen3-vl:8b` first.
- **Detection says "need to download weights"**: the first use downloads model weights; retry once the network is up.
- **Code changes don't take effect**: restart Codex (the tool list is loaded at startup).
