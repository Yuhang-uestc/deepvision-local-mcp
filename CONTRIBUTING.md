# 贡献指南

感谢你有兴趣参与！这是一个给纯文本大模型补本地视觉能力的 MCP 项目。

## 反馈问题

提 issue 时请包含：

- 运行环境：Windows 版本、Python 版本、Ollama 版本
- 复现步骤（最好带最小命令）
- 完整报错文本（不要截图截一半）
- 相关配置：模型名、是否装了可选依赖

## 开发环境

```powershell
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\install-extra.ps1   # 可选：PaddleOCR + CLIP
```

## 测试

```powershell
python tests\test_server.py        # 离线单元测试（mock Ollama）
python tests\e2e_smoke.py          # 真机冒烟（需要本机 Ollama）
```

## 代码约定

- `server.py` 保持单文件、基础路径**零第三方依赖**；重型依赖放在对应工具函数内懒加载
- 新增工具：`TOOLS` 加 schema → 写 `call_xxx()` → `handle_tools_call` 注册 → 补测试
- 所有含中文的 `.ps1` 文件必须保存为 **UTF-8 with BOM**（PowerShell 5.1 兼容）
- 提交信息用中文，格式：`类型: 简述`（feat / fix / docs / refactor / test）

## 提交流程

1. fork 并创建分支（`feat/xxx` 或 `fix/xxx`）
2. 修改 + 跑测试
3. 提交并推送，开 PR 描述改动与验证结果

## 许可注意

模型权重（yolov8*.pt 等）为 Ultralytics AGPL-3.0 许可，**不要**提交进仓库；本项目代码本身为 MIT。
