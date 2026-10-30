# -*- coding: utf-8 -*-
"""量化「国界数据」与「卫星贴图海岸线」的偏差。

做法：在 8K 贴图上裁三个区域，叠加 0.5° 经纬网格 + 国界环，
      直接看影像里的海岸落在哪条经线上、国界线又在哪条经线上。
      顺带用像素扫描算出每个纬度上"影像陆地东界"的经度，
      和 NE 数据在同一纬度的最大经度做差 —— 得到以度为单位的偏差。
"""
import glob
import json
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(ROOT, "assets", "tex", "earth-day-8k.webp")

REGIONS = {
    "js": ("江苏—盐城（滩涂）", 119.0, 122.0, 32.0, 35.0),
    "sd": ("山东半岛（岩石海岸）", 121.0, 124.0, 36.0, 38.5),
    "fj": ("福建—平潭（岩石海岸）", 117.0, 121.0, 23.0, 26.5),
}

rings = []
for p in sorted(glob.glob(os.path.join(ROOT, "geo", "c*.json"))):
    d = json.load(open(p, encoding="utf-8"))
    if "CN" in d:
        g = d["CN"]["features"][0]["geometry"]
        for poly in g["coordinates"]:
            for r in poly:
                rings.append(r)

im = Image.open(TEX).convert("RGB")
W, H = im.size
os.makedirs(os.path.join(ROOT, "shots", "borders"), exist_ok=True)


def is_sea(px):
    r, g, b = px
    # Blue Marble：海洋偏蓝且暗；陆地偏棕/绿。浑浊浅滩（黄绿）会被判成陆地 ——
    # 这本身就是要观察的现象，先按"看上去像陆地"来判。
    return b > r + 12 and b > 40 and (r + g) < 260


def east_land_edge(lat):
    """沿该纬度从东往西扫，返回第一个"影像上是陆地"的经度。"""
    y = int(round((90 - lat) / 180 * H))
    y = max(0, min(H - 1, y))
    for x in range(int((126 + 180) / 360 * W), int((115 + 180) / 360 * W), -1):
        if not is_sea(im.getpixel((x, y))):
            return -180 + (x + 0.5) / W * 360
    return None


def data_east_edge(lat):
    """NE 数据在同一纬度上的最大经度（海岸线东界）。"""
    best = None
    for r in rings:
        pts = r
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if (a[1] - lat) * (b[1] - lat) <= 0 and a[1] != b[1]:
                t = (lat - a[1]) / (b[1] - a[1])
                x = a[0] + t * (b[0] - a[0])
                if 115 <= x <= 126 and (best is None or x > best):
                    best = x
    return best


for key, (label, lon0, lon1, lat0, lat1) in REGIONS.items():
    x0 = int((lon0 + 180) / 360 * W)
    x1 = int((lon1 + 180) / 360 * W)
    y0 = int((90 - lat1) / 180 * H)
    y1 = int((90 - lat0) / 180 * H)
    crop = im.crop((x0, y0, x1, y1))
    SC = max(1, int(800 / max(crop.size)))
    if SC > 1:
        crop = crop.resize((crop.size[0] * SC, crop.size[1] * SC), Image.LANCZOS)
    cw, ch = crop.size
    dr = ImageDraw.Draw(crop)

    def px(lon, lat):
        return ((lon - lon0) / (lon1 - lon0) * cw, (lat1 - lat) / (lat1 - lat0) * ch)

    # 0.5° 网格
    v = lon0
    while v <= lon1 + 1e-6:
        gx, _ = px(v, lat0)
        dr.line([(gx, 0), (gx, ch)], fill=(120, 120, 120), width=1)
        dr.text((gx + 3, 4), "%.1fE" % v, fill=(255, 255, 255))
        v += 0.5
    v = lat0
    while v <= lat1 + 1e-6:
        _, gy = px(lon0, v)
        dr.line([(0, gy), (cw, gy)], fill=(120, 120, 120), width=1)
        dr.text((3, gy + 1), "%.1fN" % v, fill=(255, 255, 255))
        v += 0.5

    for r in rings:
        pts = [px(pt[0], pt[1]) for pt in r
               if lon0 - 0.5 <= pt[0] <= lon1 + 0.5 and lat0 - 0.5 <= pt[1] <= lat1 + 0.5]
        if len(pts) > 2:
            dr.line(pts, fill=(255, 210, 90), width=2)

    out = os.path.join(ROOT, "shots", "borders", "grid-%s.png" % key)
    crop.save(out)
    print("%-22s -> %s" % (label, out))

print("\n纬度  影像陆地东界   数据东界    差(度)   差(km)")
for lat in (32.5, 33.0, 33.5, 34.0, 34.5, 35.0, 36.5, 37.2, 24.0, 25.0):
    a = east_land_edge(lat)
    b = data_east_edge(lat)
    if a and b:
        d = a - b
        km = d * 111 * abs(__import__("math").cos(__import__("math").radians(lat)))
        print("%.1f  %10.3f  %10.3f  %+7.3f  %+7.1f" % (lat, a, b, d, km))
