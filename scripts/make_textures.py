#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 NASA 原始影像生成球面贴图（4K / 8K / 夜面 4K）。

用法：
    python scripts/make_textures.py

源图（都不进仓库，见 .gitignore 的 _tex/）：
    _tex/src/day-21600.jpg    Blue Marble Next Generation 2004-12，21600×1080…
    _tex/src/night-13500.jpg  Black Marble 2012 城市灯光，13500×6750

产出：
    assets/tex/earth-day.webp      4096×2048  首屏先用它，约 1.1MB
    assets/tex/earth-day-8k.webp   8192×4096  随后交叉淡化替换，约 3MB
    assets/tex/earth-night.webp    4096×2048  夜面城市灯光，约 350KB

为什么分两档而不是只留 8K：
    默认视角下 4096 已经够（球占屏约 86% 时贴图是 1.3 texel/px），
    但滚轮贴近看时 4096 只有 0.5 texel/px，会明显发糊；8K 才够。
    8K 纹理在显存里是 8192×4096×4 ≈ 134MB（含 mipmap 约 179MB），
    所以只在桌面端且 GPU 支持时加载，手机/小窗仍用 4K。

源图缺失底部（下载被截断）时会检测纯灰占位行并向上镜像补齐 ——
等距圆柱投影的极点是收敛点，镜像补法的视觉误差可以忽略。
"""

from __future__ import annotations

import os

from PIL import Image, ImageFile

Image.MAX_IMAGE_PIXELS = None
ImageFile.LOAD_TRUNCATED_IMAGES = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DAY = os.path.join(ROOT, "_tex", "src", "day-21600.jpg")
SRC_NIGHT = os.path.join(ROOT, "_tex", "src", "night-13500.jpg")
OUT = os.path.join(ROOT, "assets", "tex")


def fix_grey_tail(im: Image.Image) -> Image.Image:
    """把底部纯灰（128,128,128）占位行用向上镜像的内容补掉。"""
    gray = im.convert("L")
    w, h = im.size
    # 逐行判断太慢，先横向缩到 512 再判
    small = gray.resize((512, h))
    px = small.load()
    bad = 0
    for y in range(h - 1, 0, -1):
        lo, hi, s = 255, 0, 0
        for x in range(0, 512, 7):
            v = px[x, y]
            lo = min(lo, v)
            hi = max(hi, v)
            s += v
        if hi - lo <= 3 and abs(s / len(range(0, 512, 7)) - 128) < 3:
            bad += 1
        else:
            break
    if bad == 0:
        return im
    print("  底部 %d 行是截断占位，向上镜像补齐" % bad)
    for i in range(bad):
        # 第 h-1-bad+1 .. 行镜像回去
        src_y = h - bad - 1 - i
        if src_y < 1:
            src_y = 1
        band = im.crop((0, src_y, w, src_y + 1))
        im.paste(band, (0, h - bad + i))
    return im


def main() -> int:
    os.makedirs(OUT, exist_ok=True)

    if os.path.exists(SRC_DAY):
        print("[day] %s" % os.path.basename(SRC_DAY))
        im = Image.open(SRC_DAY).convert("RGB")
        print("  源尺寸 %dx%d" % im.size)
        im = fix_grey_tail(im)
        for size, name, q in (
            ((4096, 2048), "earth-day.webp", 90),
            ((8192, 4096), "earth-day-8k.webp", 88),
        ):
            out = im.resize(size, Image.LANCZOS)
            p = os.path.join(OUT, name)
            out.save(p, "WEBP", quality=q, method=6)
            print("  → %s %dx%d q%d  %.2f MB" % (
                name, size[0], size[1], q, os.path.getsize(p) / 1048576))
    else:
        print("[day] 缺少源图，跳过：%s" % SRC_DAY)

    if os.path.exists(SRC_NIGHT):
        print("[night] %s" % os.path.basename(SRC_NIGHT))
        im = Image.open(SRC_NIGHT).convert("RGB")
        im = fix_grey_tail(im)
        out = im.resize((4096, 2048), Image.LANCZOS)
        p = os.path.join(OUT, "earth-night.webp")
        out.save(p, "WEBP", quality=84, method=6)
        print("  → earth-night.webp 4096x2048 q84  %.2f MB" % (
            os.path.getsize(p) / 1048576))
    else:
        print("[night] 缺少源图，跳过：%s" % SRC_NIGHT)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
