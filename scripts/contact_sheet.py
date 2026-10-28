#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把各国地标图拼成一张联络表（contact sheet），便于一眼核对选图是否合适。

用法：
    python scripts/contact_sheet.py            # 输出 review/contact_sheet.jpg
    python scripts/contact_sheet.py --cols 4

为什么需要：
    选图是最容易出错的一步（搜到"战神广场"却没有铁塔、搜到修道院蓄水池）。
    逐张打开 12 个文件很慢，拼成一张网格后一眼就能看出哪几张不对。
"""

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CELL_W, CELL_H = 320, 240
PAD, LABEL_H = 6, 22


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--out", default=os.path.join("review", "contact_sheet.jpg"))
    ap.add_argument("--candidates", action="store_true",
                    help="改为核对 review/candidates/ 下的候选图")
    ap.add_argument("--cols-c", type=int, default=4)
    args = ap.parse_args()

    from PIL import Image, ImageDraw, ImageFont

    rows = []
    if args.candidates:
        with open(os.path.join(ROOT, "review", "candidates.json"), encoding="utf-8") as f:
            man = json.load(f)
        for iso in ("CN", "FR", "US"):
            for item in man.get(iso, []):
                for c in item.get("candidates") or []:
                    p = os.path.join(ROOT, "review", "candidates", c["file"])
                    if os.path.exists(p):
                        rows.append((iso, item["n"],
                                     "%d.%s %s" % (c["k"], item["zh"], c["origin"][:22]), p))
        cols = args.cols_c
        grid_rows = (len(rows) + cols - 1) // cols
        W = cols * (CELL_W + PAD) + PAD
        H = grid_rows * (CELL_H + LABEL_H + PAD) + PAD
        from PIL import Image as _I, ImageDraw as _D, ImageFont as _F
        try:
            font = _F.truetype("C:/Windows/Fonts/msyh.ttc", 13)
        except Exception:
            font = _F.load_default()
        sheet = _I.new("RGB", (W, H), (12, 16, 26))
        dr = _D.Draw(sheet)
        for idx, (iso, n, cap, path) in enumerate(rows):
            r, c = divmod(idx, cols)
            x = PAD + c * (CELL_W + PAD)
            y = PAD + r * (CELL_H + LABEL_H + PAD)
            im = _I.open(path).convert("RGB")
            im.thumbnail((CELL_W, CELL_H), _I.LANCZOS)
            sheet.paste(im, (x + (CELL_W - im.width) // 2, y + (CELL_H - im.height) // 2))
            dr.text((x + 2, y + CELL_H + 3), cap[:30], fill=(200, 214, 235), font=font)
        out = os.path.join(ROOT, args.out.replace("contact_sheet", "candidates_sheet"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sheet.save(out, "JPEG", quality=86)
        print("已生成 %s（%d 张候选，%dx%d）" % (
            os.path.relpath(out, ROOT), len(rows), W, H))
        for iso, n, cap, _ in rows:
            print("  %s" % cap)
        return

    for fn in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if not fn.endswith(".json") or fn in ("index.json", "landmarks.json"):
            continue
        with open(os.path.join(ROOT, "data", fn), encoding="utf-8") as f:
            rec = json.load(f)
        if not rec.get("iso_a2"):
            continue
        for i, im in enumerate(rec.get("landmark_images") or [], 1):
            p = os.path.join(ROOT, im["url"])
            if os.path.exists(p):
                rows.append((rec.get("iso_a2"), i, im.get("caption_zh") or "", p))

    if not rows:
        print("没有可用的地标图")
        return

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
    except Exception:
        font = ImageFont.load_default()

    cols = args.cols
    n = len(rows)
    grid_rows = (n + cols - 1) // cols
    W = cols * (CELL_W + PAD) + PAD
    H = grid_rows * (CELL_H + LABEL_H + PAD) + PAD
    sheet = Image.new("RGB", (W, H), (12, 16, 26))
    draw = ImageDraw.Draw(sheet)

    for idx, (iso, i, cap, path) in enumerate(rows):
        r, c = divmod(idx, cols)
        x = PAD + c * (CELL_W + PAD)
        y = PAD + r * (CELL_H + LABEL_H + PAD)
        try:
            im = Image.open(path).convert("RGB")
            im.thumbnail((CELL_W, CELL_H), Image.LANCZOS)
            ox = x + (CELL_W - im.width) // 2
            oy = y + (CELL_H - im.height) // 2
            sheet.paste(im, (ox, oy))
        except Exception as e:
            draw.text((x + 8, y + 8), "读取失败 %s" % e, fill=(220, 120, 120), font=font)
        label = "%s-%02d  %s" % (iso, i, cap)
        draw.text((x + 2, y + CELL_H + 3), label[:26], fill=(200, 214, 235), font=font)

    out = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out, "JPEG", quality=88)
    print("已生成 %s（%d 张，%dx%d）" % (args.out, n, W, H))
    for iso, i, cap, path in rows:
        print("  %s-%02d  %s" % (iso, i, cap))


if __name__ == "__main__":
    main()
