#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""寰宇图志 · 图片优化（构建期，跑在采集之后）

用法：
    python scripts/optimize_images.py CN FR US
    python scripts/optimize_images.py --all

把采集下来的大图转成 WebP 双尺寸，并把 JSON 里的路径改过去：
    详情图 760px q72   —— 面板里显示宽度约 360px，760 是 2 倍图
    缩略图 400px q74   —— 入口卡封面高 132px

为什么要单独一步：
    Wikimedia 的原图动辄 200KB+，国内直连 GitHub Pages 拉一张要 8 秒。
    录屏要求「不能出现空白加载」，所以必须压。实测 960×615 的 272KB JPEG →
    108KB + 27KB，加载 8.4s → 1.8s。

不要做的事：
    不要上采样。把 960 拉到 1000 再压，产物 228KB，几乎没省 —— 白忙。
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DETAIL_W, DETAIL_Q = 760, 72
THUMB_W, THUMB_Q = 400, 74


def optimize(iso):
    slug = iso.lower()
    adir = os.path.join(ROOT, "assets", slug)
    data_path = os.path.join(ROOT, "data", "%s.json" % slug)
    if not os.path.exists(data_path):
        print("  ! data/%s.json 不存在，跳过" % slug)
        return
    with open(data_path, encoding="utf-8") as f:
        rec = json.load(f)

    images = rec.get("landmark_images") or []
    if not images:
        print("  ! %s 没有地标图" % iso)
        return

    from PIL import Image

    changed = False
    for im_meta in images:
        src_rel = im_meta.get("url") or ""
        if not src_rel.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        src = os.path.join(ROOT, src_rel)
        if not os.path.exists(src):
            print("  ! 源图缺失 %s" % src_rel)
            continue

        base = os.path.splitext(src)[0]
        detail_rel = os.path.relpath(base + ".webp", ROOT).replace("\\", "/")
        thumb_rel = os.path.relpath(base + ".thumb.webp", ROOT).replace("\\", "/")

        img = Image.open(src).convert("RGB")
        orig = os.path.getsize(src)

        def save(w, dest, q):
            w2 = min(w, img.width)          # 绝不放大
            h2 = round(img.height * w2 / img.width)
            img.resize((w2, h2), Image.LANCZOS).save(dest, "WEBP", quality=q, method=6)
            return os.path.getsize(dest), (w2, h2)

        s1, d1 = save(DETAIL_W, os.path.join(ROOT, detail_rel), DETAIL_Q)
        s2, d2 = save(THUMB_W, os.path.join(ROOT, thumb_rel), THUMB_Q)

        im_meta["url"] = detail_rel
        im_meta["thumb_url"] = thumb_rel
        im_meta["bytes"] = s1
        im_meta["thumb_bytes"] = s2
        im_meta["size"] = {"detail": "%dx%d" % d1, "thumb": "%dx%d" % d2}
        im_meta["encoding"] = "webp q%d/q%d (源 %dx%d %.0fKB JPEG)" % (
            DETAIL_Q, THUMB_Q, img.width, img.height, orig / 1024)
        changed = True
        print("  ✓ %s  %.0f KB → 详情 %dKB + 缩略 %dKB  (省 %.0f%%)" % (
            src_rel, orig / 1024, s1 / 1024, s2 / 1024,
            100 - (s1 + s2) * 100 / orig))

    if not changed:
        print("  - 无需处理")
        return

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")

    idx_path = os.path.join(ROOT, "data", "index.json")
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
        for c in idx.get("countries", []):
            if c.get("iso_a2", "").upper() == iso.upper() and images:
                c["thumb"] = images[0].get("thumb_url")
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("  ✓ data/index.json 缩略图已同步")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("isos", nargs="*", help="ISO 码，如 CN FR US")
    ap.add_argument("--all", action="store_true", help="处理 data/ 下全部档案")
    args = ap.parse_args()

    isos = [x.upper() for x in args.isos]
    if args.all:
        d = os.path.join(ROOT, "data")
        isos = [os.path.splitext(f)[0].upper() for f in os.listdir(d)
                if f.endswith(".json") and f != "index.json"]
    if not isos:
        ap.error("给个 ISO 码，或用 --all")

    for iso in isos:
        print("[%s]" % iso)
        optimize(iso)


if __name__ == "__main__":
    main()
