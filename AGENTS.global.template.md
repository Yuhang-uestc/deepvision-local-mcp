<!-- deepvision-local-mcp:start -->
## 本机识图工具（仅涉及图片任务时参考）

当用户要求分析 / 识别 / 描述图片时，本机有现成工具，直接使用，不要另写脚本：

- 入口：`python __CALL_TOOL_PATH__ <工具名> '<JSON 参数>'`
- 常用：看图 `analyze_image`（mode=quick）｜文字 `ocr_extract`（engine=auto）｜数人 `detect_objects`｜尺寸 `image_info`｜排障 `vision_status`
- 大图（宽 >1500px）先 quick 概览；同一时间只跑一个本地模型推理。

**仅此而已**：其它任务（写代码、问答、文档等）不受本节任何影响。
<!-- deepvision-local-mcp:end -->
