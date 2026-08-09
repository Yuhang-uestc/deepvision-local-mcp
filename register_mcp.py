#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全注册 local_vision MCP 到 Codex 配置。

用法：
    python register_mcp.py [--config 配置路径] [--python Python绝对路径] [--server server.py路径] [--force]

安全设计：
- 只修改 [mcp_servers.local_vision] 这一节（其它内容一个字节不动）；
- 修改前自动备份（.bak-时间戳），改完自动 tomllib 校验，校验失败自动回滚；
- 检测到 Codex 正在运行会中止（除非 --force）——运行中的应用可能用旧配置覆盖外部修改。

退出码：0 = 成功/无需改动；1 = 失败；2 = 检测到 Codex 运行而中止。
"""

import argparse
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path


SECTION = "mcp_servers.local_vision"


def detect_eol(text):
    return "\r\n" if "\r\n" in text else "\n"


def read_config(path):
    raw = Path(path).read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    cfg = tomllib.loads(text)
    return raw, has_bom, text, cfg


def find_section(lines, name):
    """返回节的行范围 [start, end)（end 为下一节头或文件末尾）。"""
    start = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]") and s[1:-1].strip() == name:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        s = lines[i].strip()
        if s.startswith("[") and s.endswith("]"):
            end = i
            break
    return start, end


def field_key(line):
    """取 TOML 键名：'command = ...' -> 'command'；非赋值行返回 None。"""
    if "=" not in line:
        return None
    key = line.split("=", 1)[0].strip().strip('"').strip()
    return key or None


def edit_section(lines, start, end, python_path, server_path):
    """只重建 local_vision 节的 command/args 两行，其它行原样保留。"""
    fields = {"command": False, "args": False}
    for i in range(start, end):
        key = field_key(lines[i])
        if key in fields:
            fields[key] = True

    out = []
    for i, line in enumerate(lines):
        if start <= i < end:
            key = field_key(line)
            if key == "command":
                out.append(f'command = "{python_path}"')
                continue
            if key == "args":
                out.append(f'args = ["{server_path}"]')
                continue
        out.append(line)

    if not fields["command"] or not fields["args"]:
        hdr = next(
            (j for j, l in enumerate(out) if l.strip().startswith(f"[{SECTION}]")),
            None,
        )
        if hdr is not None:
            ins = []
            if not fields["command"]:
                ins.append(f'command = "{python_path}"')
            if not fields["args"]:
                ins.append(f'args = ["{server_path}"]')
            out[hdr + 1 : hdr + 1] = ins
    return out


def codex_running():
    try:
        out = subprocess.run(
            ["tasklist"], capture_output=True, text=True, errors="replace", timeout=10
        ).stdout.lower()
        return "codex" in out
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser(description="安全注册 local_vision MCP")
    ap.add_argument("--config", default=str(Path.home() / ".codex" / "config.toml"))
    ap.add_argument("--python", default="", help="要写入的 Python 绝对路径（默认用当前解释器）")
    ap.add_argument("--server", default="", help="server.py 绝对路径（默认取本脚本同目录）")
    ap.add_argument("--force", action="store_true", help="即使检测到 Codex 运行也继续")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"FAIL: 找不到 Codex 配置 {cfg_path}")
        return 1

    python_path = args.python.strip() or sys.executable
    python_toml = python_path.replace("\\", "/")
    server_path = args.server.strip() or str(Path(__file__).resolve().parent / "server.py")
    server_toml = server_path.replace("\\", "/")

    raw, has_bom, text, cfg = read_config(cfg_path)
    lv = (cfg.get("mcp_servers") or {}).get("local_vision") or {}
    lv_ok = (
        bool(lv)
        and lv.get("command") == python_toml
        and list(lv.get("args") or []) == [server_toml]
    )
    if lv_ok:
        print("OK: local_vision 已注册且路径正确，无需改动。")
        return 0

    if codex_running() and not args.force:
        print(
            "ABORT: 检测到 Codex 正在运行。先完全退出 Codex 再运行本脚本，"
            "否则运行中的应用可能用旧配置覆盖你的修改。\n"
            "（确定要强制继续可加 --force）"
        )
        return 2

    eol = detect_eol(text)
    lines = text.split(eol)
    span = find_section(lines, SECTION)

    backup = cfg_path.with_name(
        f"{cfg_path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    shutil.copy2(cfg_path, backup)
    print(f"已备份配置：{backup}")

    if span is None:
        block = (
            f"[{SECTION}]{eol}"
            f'command = "{python_toml}"{eol}'
            f'args = ["{server_toml}"]{eol}'
        )
        new_text = text
        if new_text and not new_text.endswith(eol):
            new_text += eol
        new_text += block
    else:
        start, end = span
        new_lines = edit_section(lines, start, end, python_toml, server_toml)
        new_text = eol.join(new_lines)

    new_bytes = (b"\xef\xbb\xbf" if has_bom else b"") + new_text.encode("utf-8")
    try:
        tomllib.loads(new_text)  # 写前先校验语法
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: 修改后的配置解析失败（{e}），已回滚，未写入。")
        return 1

    cfg_path.write_bytes(new_bytes)

    try:
        _, _, _, new_cfg = read_config(cfg_path)
        lv2 = (new_cfg.get("mcp_servers") or {}).get("local_vision") or {}
        if lv2.get("command") == python_toml and list(lv2.get("args") or []) == [server_toml]:
            print(f"OK: local_vision 已注册。command = {python_toml}")
            return 0
        raise ValueError("校验不一致")
    except Exception as e:  # noqa: BLE001
        cfg_path.write_bytes(raw)  # 回滚
        print(f"FAIL: 写入后校验失败（{e}），已自动回滚到原配置。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
