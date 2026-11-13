# -*- coding: utf-8 -*-
"""把 assets/tex 里每张贴图的**内容 md5** 写进 index.html 的 TEX_VER 表。

为什么要有这一步
----------------
贴图 URL 原来挂的是全局构建号（?v=2026-11-11-AW）。构建号每次发版都变，
哪怕只改了一行 CSS，浏览器的缓存也全部作废 —— 回访用户要把两张 8K 贴图
（合计约 2MB）整套重下一遍。华为云的流量告警就是这么被刷出来的。

改成内容哈希之后：图片没重新生成 → 哈希不变 → URL 不变 → 直接命中缓存；
只有真的重新生成过的那张才会换 URL。

用法（重新生成任何 assets/tex 下的图之后都要跑一次）
----------------------------------------------------
    python scripts/stamp_tex_ver.py           # 写入
    python scripts/stamp_tex_ver.py --check   # 只报告是否一致（CI / 发版前）
"""
import argparse
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")
TEXDIR = os.path.join(ROOT, "assets", "tex")
START = "    /* TEX_VER:start */"
END = "    /* TEX_VER:end */"


def collect():
    """只收 index.html 里真正引用到的贴图（tex / texLo 字段）。"""
    html = open(HTML, encoding="utf-8").read()
    names = sorted(set(re.findall(r"tex(?:Lo)?:\s*'([^']+)'", html)))
    out = []
    for n in names:
        p = os.path.join(TEXDIR, n)
        if not os.path.isfile(p):
            print("  缺少文件:", n)
            continue
        h = hashlib.md5(open(p, "rb").read()).hexdigest()[:8]
        out.append((n, h, os.path.getsize(p)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    a = ap.parse_args()

    items = collect()
    if not items:
        print("没找到任何贴图引用")
        return 1

    body = "".join("    '%s': '%s',\n" % (n, h) for n, h, _ in items)
    html = open(HTML, encoding="utf-8").read()
    i, j = html.find(START), html.find(END)
    if i < 0 or j < 0:
        print("index.html 里找不到 TEX_VER 标记")
        return 1
    new = html[:i + len(START)] + "\n" + body + html[j:]

    changed = [n for n, h, _ in items if ("'%s': '%s'" % (n, h)) not in html[i:j]]
    for n, h, sz in items:
        print("  %-18s %s  %7.1f KB %s" % (n, h, sz / 1024,
                                            "（新）" if n in changed else ""))
    if new == html:
        print("版本表已是最新")
        return 0
    if a.check:
        print("版本表过期，需要跑一次 stamp_tex_ver.py")
        return 2
    open(HTML, "w", encoding="utf-8", newline="").write(new)
    print("已更新 index.html 的 TEX_VER（%d 张）" % len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
