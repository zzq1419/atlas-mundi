#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证 FunctionGraph 上的检索 API。

用法：
    python scripts/call_fg.py --url "https://xxx.apig.cn-east-3.huaweicloud.com/..." --q "长城"
    python scripts/call_fg.py --url "https://..." --full      # 跑 7 条并逐条比对期望

期望值来自本地 handler 的实测输出（与前端 JS 逐条比对过 14/14 一致），
所以云端只要结果不同，就说明部署有问题（入口写错、代码没更新、数据没传）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# (查询, 期望条数, 期望首条 country, 期望首条问题前若干字)
EXPECT = [
    ("长城", 3, "中国", "长城是什么时候建的"),
    ("说什么语言", 3, "美国", "美国说什么语言"),
    ("面积多大", 3, "中国", "中国面积多大"),
    ("奶酪", None, "法国", "法国人平时吃什么"),
    ("世俗性", None, "法国", "法国有什么传统习俗"),
    ("极光", 0, None, None),
    ("日本有什么", 0, None, None),
]


def call(url: str, q: str, method: str = "GET", timeout: int = 20) -> tuple[int, dict | str, int]:
    t0 = time.time()
    try:
        if method == "GET":
            full = url + ("&" if "?" in url else "?") + "q=" + urllib.parse.quote(q)
            req = urllib.request.Request(full, method="GET")
        else:
            body = json.dumps({"q": q}, ensure_ascii=False).encode()
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        code = e.code
    except Exception as e:
        return 0, str(e)[:160], int((time.time() - t0) * 1000)
    ms = int((time.time() - t0) * 1000)
    try:
        return code, json.loads(raw), ms
    except json.JSONDecodeError:
        return code, raw[:300], ms


def main() -> int:
    ap = argparse.ArgumentParser(description="验证 FunctionGraph 检索 API")
    ap.add_argument("--url", required=True, help="API 网关返回的调用地址")
    ap.add_argument("--q", help="单条查询")
    ap.add_argument("--full", action="store_true", help="跑 7 条并比对期望")
    ap.add_argument("--method", default="GET", choices=["GET", "POST"])
    a = ap.parse_args()

    if a.q:
        code, body, ms = call(a.url, a.q, a.method)
        print("HTTP %s  %d ms" % (code, ms))
        if isinstance(body, dict):
            print(json.dumps(body, ensure_ascii=False, indent=2)[:1200])
        else:
            print(str(body)[:600])
        return 0 if code == 200 else 1

    if not a.full:
        ap.print_help()
        return 0

    print("== 逐条比对（期望值取自本地 handler 实测）==\n")
    ok = 0
    for q, want_n, want_country, want_q in EXPECT:
        code, body, ms = call(a.url, q, a.method)
        if code != 200 or not isinstance(body, dict):
            print("  ✗ %-12s HTTP %s  %s" % (q, code, str(body)[:80]))
            continue
        n = body.get("count", 0)
        issues = []
        if want_n is not None and n != want_n:
            issues.append("条数 %d≠%d" % (n, want_n))
        if want_country:
            first = (body.get("results") or [{}])[0]
            if first.get("country") != want_country:
                issues.append("首条国家 %s≠%s" % (first.get("country"), want_country))
            if want_q and not str(first.get("q") or "").startswith(want_q):
                issues.append("首条问题不符")
        if n == 0 and not body.get("note"):
            issues.append("空结果缺 note 说明")

        if issues:
            print("  ✗ %-12s %s  (%d ms)" % (q, "；".join(issues), ms))
        else:
            head = "" if n == 0 else "首条「%s」" % (body["results"][0]["q"][:22])
            print("  ✓ %-12s %d 条 %s  (%d ms)" % (q, n, head, ms))
            ok += 1

    print("\n%d/%d 通过" % (ok, len(EXPECT)))
    if ok == len(EXPECT):
        print("云端与本地结果完全一致 —— 部署无误。")
    return 0 if ok == len(EXPECT) else 1


if __name__ == "__main__":
    sys.exit(main())
