#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把人工选定的候选图落到 assets/，并更新 data/{iso}.json。

用法：
    python scripts/assemble.py            # 读 review/choices.json
    python scripts/assemble.py --list     # 只列候选，方便决定选哪个

review/choices.json 格式（每国按地标顺序给候选文件名）：
    {
      "CN": ["CN_01_1.jpg", "CN_02_3.jpg", "CN_03_1.jpg", "CN_04_2.jpg"],
      "FR": [...],
      "US": [...]
    }

这一步不联网：候选图已在 review/candidates/ 里，元数据在 review/candidates.json 里。
"""

import argparse
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAND = os.path.join(ROOT, "review", "candidates")


def load():
    with open(os.path.join(ROOT, "review", "candidates.json"), encoding="utf-8") as f:
        man = json.load(f)
    idx = {}
    for iso, items in man.items():
        for item in items:
            for c in item.get("candidates") or []:
                idx[c["file"]] = dict(c, iso=iso, n=item["n"], zh=item["zh"])
    return man, idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    man, idx = load()

    if args.list:
        for iso, items in man.items():
            print("[%s]" % iso)
            for item in items:
                print("  %d. %s" % (item["n"], item["zh"]))
                for c in item.get("candidates") or []:
                    print("      %d) %-18s %.2f分 %dx%d  %s" % (
                        c["k"], c["file"], c["score"],
                        c.get("width") or 0, c.get("height") or 0, c["origin"][:44]))
        return

    cpath = os.path.join(ROOT, "review", "choices.json")
    if not os.path.exists(cpath):
        print("还没写 review/choices.json。先跑 --list 看候选，再按格式填。")
        return
    with open(cpath, encoding="utf-8") as f:
        choices = json.load(f)

    for iso, files in choices.items():
        slug = iso.lower()
        adir = os.path.join(ROOT, "assets", slug)
        os.makedirs(adir, exist_ok=True)
        dpath = os.path.join(ROOT, "data", "%s.json" % slug)
        with open(dpath, encoding="utf-8") as f:
            rec = json.load(f)

        images = []
        for i, fn in enumerate(files, 1):
            info = idx.get(fn)
            if not info:
                print("  ! %s 不在候选清单里，跳过" % fn)
                continue
            src = os.path.join(CAND, fn)
            if not os.path.exists(src):
                print("  ! 候选文件缺失 %s" % fn)
                continue
            ext = os.path.splitext(fn)[1].lower()
            dst_rel = "assets/%s/L%02d%s" % (slug, i, ext)
            shutil.copyfile(src, os.path.join(ROOT, dst_rel))
            images.append({
                "title": "File:" + info["origin"],
                "caption_zh": info["zh"],
                "caption": info["zh"],
                "url": dst_rel,
                "thumb_url": dst_rel,
                "remote_url": info.get("remote_url"),
                "source": info.get("source"),
                "author": info.get("author"),
                "license": info.get("license"),
                "license_url": None,
                "license_status": "ok" if info.get("license") else "unknown",
                "load_verified": False,
                "bytes": os.path.getsize(os.path.join(ROOT, dst_rel)),
                "picked_from":  info.get("source"),
                "origin_size": "%sx%s" % (info.get("width"), info.get("height")),
            })
            print("  ✓ %s ← %s  %s" % (dst_rel, fn, info["origin"][:44]))

        if not images:
            print("  ! %s 一张都没落，跳过" % iso)
            continue

        rec["landmark_images"] = images
        rec["image_license"] = images[0].get("license")
        rec["review_notes"] = [n for n in (rec.get("review_notes") or [])
                               if "地标图" not in n]
        rec["review_notes"].append("地标图由人工从候选中挑选（%d 张，中文图注）" % len(images))
        with open(dpath, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
            f.write("\n")

    print("\n下一步：python scripts/optimize_images.py --all && python scripts/sync_index.py")


if __name__ == "__main__":
    main()
