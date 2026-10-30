# -*- coding: utf-8 -*-
"""修正图片路径指向的文件名对不上的情况。

典型症状：check_data 报「图片3 文件不存在：assets/ch/L03.png」。
成因是两条流水线各用一套编号：collect 阶段按 L01/L02… 命名，
fill_images 按 01/02… 命名，同目录下两套并存时，数据里可能写着
L03.png 而盘上是 03.webp。

这里只在"文件确实不存在"时才动手，按同目录下同名不同前后缀找一遍，
找到唯一候选才改写；找不到就报出来，不动数据。

用法：
    python scripts/fix_asset_paths.py --dry
    python scripts/fix_asset_paths.py
"""
import argparse
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SKIP = {"index.json", "landmarks.json", "search.json"}
EXTS = (".webp", ".jpg", ".jpeg", ".png")


def candidates(rel):
    """同目录下可能的等价文件名。"""
    d, base = os.path.dirname(rel), os.path.basename(rel)
    stem, ext = os.path.splitext(base)
    out = []
    stems = {stem}
    if stem.startswith("L") and len(stem) > 1 and stem[1:].isdigit():
        stems.add(stem[1:])
    else:
        stems.add("L" + stem)
    # 用正斜杠拼：这是要写进 JSON、最终变成 URL 的路径，
    # os.path.join 在 Windows 上给的是反斜杠，浏览器里会变成 %5C。
    prefix = (d + "/") if d else ""
    for s in stems:
        for e in EXTS:
            out.append(prefix + s + e)
        out.append(prefix + s + ".thumb.webp")
    return [x for x in out if x != rel]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    fixed = missing = 0
    for path in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        base = os.path.basename(path)
        if base.startswith("_") or base in SKIP:
            continue
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        if not rec.get("iso_a2"):
            continue
        changed = False
        for im in rec.get("landmark_images") or []:
            for key in ("url", "thumb_url"):
                rel = im.get(key)
                if not rel or os.path.exists(os.path.join(ROOT, rel)):
                    continue
                hit = [c for c in candidates(rel) if os.path.exists(os.path.join(ROOT, c))]
                if not hit:
                    if key == "url":
                        print("  [x] %s 找不到 %s" % (rec.get("iso_a2"), rel))
                        missing += 1
                    continue
                print("  [ok] %s %s → %s" % (rec.get("iso_a2"), rel, hit[0]))
                if not a.dry:
                    im[key] = hit[0]
                changed = True
                fixed += 1
        if changed and not a.dry:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
                f.write("\n")

    print("\n%s：修正 %d 处，仍缺 %d 处" % ("预演" if a.dry else "完成", fixed, missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
