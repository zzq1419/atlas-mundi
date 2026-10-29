#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把用户给的点阵球原图处理成站点 logo 与标签页图标。

为什么不自己画：手写的 Fibonacci 点阵远看能唬人，凑近就不是那张图了 ——
点的大小、边缘那圈粘连、中间的留白，都是原图里摆好的。直接贴最准。

原图是纯黑底（四角像素值 0）上的白点阵，所以：
  * logo      把黑底抠成透明（alpha = 亮度），白点在深色/浅色背景上都能贴
  * favicon   保留黑底，球缩到 58% 居中，四周留黑 —— 标签页 16px 下要的是
              一个"黑块 + 白点球"的形状，不是一颗撑满的球

用法：
    python scripts/make_logo.py "C:/Users/Admin/Downloads/xxx.jpg"
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_LOGO = os.path.join(ROOT, "assets", "logo.png")
OUT_FAV = os.path.join(ROOT, "assets", "favicon.png")


def square_crop(im):
    """按亮点包围盒切一个正方形，四周留 8% 呼吸空间。"""
    g = im.convert("L")
    w, h = g.size
    px = g.load()
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if px[x, y] > 40:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    side = max(maxx - minx, maxy - miny) * 1.08
    side = min(side, min(w, h))
    return im.crop((int(cx - side / 2), int(cy - side / 2),
                    int(cx + side / 2), int(cy + side / 2)))


def cutout(im, size=128):
    """黑底抠透明：亮度当 alpha，颜色统一刷白，抗锯齿边缘自然保留。"""
    im = im.convert("RGB").resize((size, size), Image.LANCZOS)
    g = im.convert("L")
    alpha = g.point(lambda v: 0 if v < 22 else min(255, int((v - 22) * 255 / 120)))
    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    white.putalpha(alpha)
    return white


def favicon(logo, size=192, scale=0.58):
    """黑底 + 圆角 + 居中的球。"""
    canvas = Image.new("RGBA", (size, size), (5, 7, 12, 255))
    inner = int(size * scale)
    ball = logo.resize((inner, inner), Image.LANCZOS)
    canvas.alpha_composite(ball, ((size - inner) // 2, (size - inner) // 2))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(size * 0.22), fill=255)
    mask = mask.filter(ImageFilter.SMOOTH)
    canvas.putalpha(mask)
    return canvas


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else ""
    if not src or not os.path.exists(src):
        print("用法：python scripts/make_logo.py <点阵球原图>")
        return 1
    sq = square_crop(Image.open(src))
    logo = cutout(sq, 128)
    logo.save(OUT_LOGO)
    fav = favicon(logo, 192, 0.58)
    fav.save(OUT_FAV)
    print("logo.png     %5.1f KB  %dx%d  透明底白点阵"
          % (os.path.getsize(OUT_LOGO) / 1024, logo.size[0], logo.size[1]))
    print("favicon.png  %5.1f KB  %dx%d  黑底，球占 58%%"
          % (os.path.getsize(OUT_FAV) / 1024, fav.size[0], fav.size[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
