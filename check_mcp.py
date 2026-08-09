#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP 注册探针：读取 Codex 配置里的 local_vision，真实启动 server 并握手，确认工具可列出。

用法：
    python check_mcp.py [--config 配置路径]

退出码：0 = 正常；1 = 配置缺失 / 服务连不上 / 工具列表异常。
"""

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path


DEFAULT_CONFIG = Path.home() / ".codex" / "config.toml"
EXPECTED_MIN_TOOLS = 10


def main():
    ap = argparse.ArgumentParser(description="MCP 注册与连通性探针")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="Codex 配置路径")
    args = ap.parse_args()
    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"FAIL: 找不到 Codex 配置 {cfg_path}")
        return 1
    try:
        cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: 配置解析失败：{e}")
        return 1

    svc = (cfg.get("mcp_servers") or {}).get("local_vision")
    if not svc:
        print("FAIL: 配置中未找到 [mcp_servers.local_vision]，请先运行 register-mcp.ps1")
        return 1
    command = str(svc.get("command", "")).strip()
    args_list = [str(a) for a in (svc.get("args") or [])]
    print(f"配置: command = {command}")
    print(f"      args   = {args_list}")
    if not command:
        print("FAIL: command 为空")
        return 1
    if command.lower() == "python":
        print("WARN: command 是裸 'python'，建议重跑 register-mcp.ps1 升级为 Python 绝对路径")
    if not args_list:
        print("FAIL: args 为空，缺少 server.py 路径")
        return 1

    cmd = [command] + args_list
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        print(f"FAIL: 无法启动 {command}：{e}")
        return 1

    try:
        def send(obj):
            proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            proc.stdin.flush()

        def recv():
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("server 未返回（可能启动失败），请查看 stderr")
            return json.loads(line)

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        init = recv()
        version = (init.get("result") or {}).get("serverInfo", {}).get("version", "?")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools_resp = recv()
        tools = (tools_resp.get("result") or {}).get("tools") or []
        names = [t.get("name", "?") for t in tools]
        print(f"OK: 服务启动成功（server 版本 v{version}），共 {len(tools)} 个工具")
        print("工具:", ", ".join(names))
        if len(tools) < EXPECTED_MIN_TOOLS:
            print(f"FAIL: 工具数量异常（{len(tools)} < {EXPECTED_MIN_TOOLS}），请重启 Codex 后重试")
            return 1
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: 握手失败：{e}")
        return 1
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
