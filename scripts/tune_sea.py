# -*- coding: utf-8 -*-
"""给卫星底图做"浑水校正"：把海岸线以外的黄褐色浅海压成正常海色。

为什么需要：
    Blue Marble 2004 在江苏外海拍到的是一大片含沙浑水（长江、淮河、旧黄河口），
    颜色和岸上的土地几乎一样 —— 于是国界线贴着海岸画，视觉上却像"切进了内陆"。
    夜光图可以证明那片没有灯、是海；但用户看图时不会先看夜光图。

做法：
    1. 用 Natural Earth 10m land 多边形栅格化成海陆掩膜（8192×4096）
    2. 只在「海里 且 又亮又不蓝」的像素上动手（= 浑水），把它们拉向深海色
    3. 陆地、深海、夜间灯光一律不动

不改矢量数据 —— 金线的位置本来就是对的。
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 掩膜用我们自己发布的国界分片（geo/c*.json）：结构统一、坐标已验证。
# 直接读 Natural Earth 的 ne_10m_land 反而踩坑 —— 那份文件的 MultiPolygon
# 层级与常规写法不一致，照标准层级解析会把"环的列表"当成环去填，结果
# 掩膜整体错位（北京被当成海、几内亚湾被当成陆地）。
LAND = os.path.join(ROOT, "geo", "c*.json")
W, H = 8192, 4096
MASK = os.path.join(ROOT, "_tex", "landmask-8k.png")



def build_mask():
    if os.path.exists(MASK):
        return Image.open(MASK)
    m = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(m)
    n = 0
    for path in sorted(glob.glob(LAND)):
        with open(path, encoding="utf-8") as f:
            chunk = json.load(f)
        for iso, fc in chunk.items():
            for feat in fc.get("features") or []:
                g = feat.get("geometry") or {}
                polys = [g["coordinates"]] if g.get("type") == "Polygon" else (g.get("coordinates") or [])
                for poly in polys:
                    for ring in poly:
                        if len(ring) < 3:
                            continue
                        lons = [p[0] for p in ring]
                        if max(lons) - min(lons) > 180:
                            continue                      # 跨日线的环（南极洲绕地球一圈）
                        pts = [((p[0] + 180) / 360 * W, (90 - p[1]) / 180 * H) for p in ring]
                        dr.polygon(pts, fill=255)
                        n += 1
    os.makedirs(os.path.dirname(MASK), exist_ok=True)
    m.save(MASK)
    print("掩膜：%d 个环 -> %s" % (n, MASK))
    return m


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "tex", "earth-day-8k.webp")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "_tex", "day-8k-tuned.webp")

    mask = build_mask()
    sea = np.array(mask, dtype=np.uint8) < 128           # True = 海
    im = Image.open(src).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)
    arr = np.asarray(im).astype(np.float32)

    # 浑浊判据：在海里，够亮，且不偏蓝（蓝通道没有明显高过红）
    lum = arr.mean(axis=2)
    lat = 90.0 - (np.arange(H) + 0.5) / H * 180.0          # 每行的纬度
    band = (np.abs(lat) < 62)[:, None] & np.ones((1, W), bool)   # 浑水只出现在中低纬河口
    muddy = sea & band & (lum > 55) & (arr[:, :, 2] < arr[:, :, 0] + 18)
    # 越亮越浑，混得越狠；上限 0.9 保留一点纹理，不至于糊成纯色
    alpha = np.clip((lum - 55) / 70.0, 0, 1) * 0.90
    alpha = np.where(muddy, alpha, 0.0)[:, :, None]

    # 目标色用「周围海水的颜色」，而不是一个写死的深蓝 ——
    # 写死的话，浑水会被拉成一块突兀的灰蓝，和外侧深海之间出现一条硬边。
    # 这里把海域单独模糊（半径约 1.5°，比浑水带宽），浑水就被拉向它所在的那片海。
    from PIL import ImageFilter

    def blur_plane(plane, radius=48):
        im8 = Image.fromarray(np.clip(plane, 0, 255).astype(np.uint8))
        return np.asarray(im8.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)

    wmask = blur_plane(sea.astype(np.float32) * 255.0) / 255.0
    wmask = np.maximum(wmask, 1e-3)[:, :, None]
    tgt = np.stack([blur_plane(arr[:, :, i] * sea.astype(np.float32)) for i in range(3)],
                   axis=2) / wmask

    out = arr * (1 - alpha) + tgt * alpha
    out = np.clip(out, 0, 255).astype(np.uint8)

    changed = int((alpha[:, :, 0] > 0.05).sum())
    print("调整像素 %d（占全球 %.2f%%）" % (changed, 100.0 * changed / (W * H)))
    im2 = Image.fromarray(out)
    im2.save(dst, quality=82, method=6)
    print("->", dst, "%.1f MB" % (os.path.getsize(dst) / 1048576.0))


if __name__ == "__main__":
    main()
