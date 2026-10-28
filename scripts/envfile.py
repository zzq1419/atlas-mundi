#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""读仓库根的 `.env`，把 KEY=VALUE 塞进 os.environ。

为什么单独一个文件：`llm.py / collect_all.py / step1 / step2` 都需要 key 和模型名，
而 `.env` 已经在 .gitignore 里。写一份加载器、四处 import，比在每个脚本里复制一遍稳。

规则
----
* 一行一条 `KEY=VALUE`，`#` 开头是注释；
* **已存在的环境变量优先** —— 命令行里 `set DEEPSEEK_API_KEY=...` 不会被 .env 覆盖；
* 值两端的引号会去掉（Windows 下很容易把引号一起写进去）；
* 读不到 `.env` 就当没有，不报错（CI 里靠真实环境变量）。
"""

from __future__ import annotations

import os

_CACHE = {"loaded": False}


def load(force: bool = False) -> dict:
    """加载仓库根的 .env，返回本次新设置的键值。"""
    if _CACHE["loaded"] and not force:
        return {}
    _CACHE["loaded"] = True

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".env")
    added = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if not k or not v:
                    continue
                if not os.environ.get(k):
                    os.environ[k] = v
                    added[k] = v
    except OSError:
        pass
    return added


def mask(v: str) -> str:
    """打日志用：只露前 6 位。"""
    v = (v or "").strip()
    return (v[:6] + "…" + v[-4:]) if len(v) > 12 else ("(空)" if not v else "…")
