#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 3D 地球专用数据 geo/globe.json。

为什么不直接用 geo/{iso}.geojson 与 ne_110m_land.geojson：

1. **体积**。GeoJSON 的 FeatureCollection 结构对球面渲染是纯冗余 —— 我们只
   需要环（环 = 经纬度点串），所有 properties 都用不上。原文件 135+237KB，
   压缩成纯环数组后约 1/4。

2. **经度跨 180° 的断点**。美国阿留申群岛、俄罗斯楚科奇跨经度 180°，相邻两点
   经度从 179 跳到 -179。若直接连直线，球面上会出现一条横贯全球的假线。这里
   预先标记断点（用 null 分隔同一环内的多段），前端不必再猜。

3. **精度统一**。球面显示时 0.01° 约等于 1km，2 位小数足够；0.001° 是像素级
   以下，纯浪费。统一截断到 2 位，可用 gzip 进一步压缩。

输出结构：

    {
      "generated": "2026-10-26",
      "land":      [ ring, ring, ... ],            # 大陆轮廓，背景参照
      "countries": [ {iso, name, center, rings}, ... ]
    }

每个 ring 是 [lon, lat] 数组；若环内有跨日期变更线的断点，用 null 分隔成多段。
"""
import json
import math
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(ROOT, "geo")
OUT = os.path.join(GEO, "globe.json")

COUNTRIES = [("CN", "中国"), ("FR", "法国"), ("US", "美国")]

# 球面显示时 0.01° ≈ 1.1km，屏幕上不足一个像素
PRECISION = 2
# 抽稀容差（度）。0.05° ≈ 5.5km，球体半径 1 时相当于 0.001 弧度，肉眼无差别
TOLERANCE = 0.05


def dp_simplify(points, tol):
    """Douglas-Peucker 抽稀。球面渲染不需要 50m 级精度，
    一个环从 2000 点降到 200 点，视觉上分不出来，但帧率差一倍。"""
    if len(points) < 3:
        return points

    def perp_dist(p, a, b):
        # 经纬度平面内的垂直距离（小范围内近似成立）
        ax, ay = a
        bx, by = b
        px, py = p
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    # 迭代版，避免长环递归爆栈
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        dmax, idx = 0.0, -1
        for i in range(lo + 1, hi):
            d = perp_dist(points[i], points[lo], points[hi])
            if d > dmax:
                dmax, idx = d, i
        if dmax > tol and idx > 0:
            keep[idx] = True
            stack.append((lo, idx))
            stack.append((idx, hi))
    return [p for p, k in zip(points, keep) if k]


def split_antimeridian(ring):
    """把跨经度 180° 的环切成多段，用 None 作为断点标记。

    判据：相邻两点经度差绝对值 > 180°，说明它们在球面上其实很近
    （179° → -179° 实际只差 2°），但平面连线会横穿整个地图。
    """
    segs, cur = [], [ring[0]]
    for i in range(1, len(ring)):
        if abs(ring[i][0] - ring[i - 1][0]) > 180:
            segs.append(cur)
            cur = [ring[i]]
        else:
            cur.append(ring[i])
    segs.append(cur)
    return segs


def ring_out(ring):
    """环 → 输出格式。跨 180° 时返回多段（段间插 null）。"""
    ring = dp_simplify(ring, TOLERANCE)
    if len(ring) < 3:
        return None
    segs = split_antimeridian(ring)
    if len(segs) == 1:
        return [[round(x, PRECISION), round(y, PRECISION)] for x, y in segs[0]]
    out = []
    for i, seg in enumerate(segs):
        if i:
            out.append(None)          # 断点
        out.extend([[round(x, PRECISION), round(y, PRECISION)] for x, y in seg])
    return out


def rings_of(geometry):
    """Polygon / MultiPolygon → 外环列表（内环不参与球面线条绘制）。"""
    if not geometry:
        return []
    t = geometry.get("type")
    if t == "Polygon":
        return [geometry["coordinates"][0]] if geometry.get("coordinates") else []
    if t == "MultiPolygon":
        return [poly[0] for poly in geometry.get("coordinates") or [] if poly]
    return []


def collect_land():
    p = os.path.join(GEO, "_ne_110m_land.geojson")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    rings = []
    for feat in data.get("features") or []:
        for ring in rings_of(feat.get("geometry")):
            out = ring_out(ring)
            if out:
                rings.append(out)
    return rings


def collect_country(iso):
    p = os.path.join(GEO, "%s.geojson" % iso.lower())
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    rings = []
    for feat in data.get("features") or []:
        for ring in rings_of(feat.get("geometry")):
            out = ring_out(ring)
            if out:
                rings.append(out)

    # 标签位置必须用**最大环**（本土）的包围盒中心，不能用全部顶点的均值。
    # 实测：法国的海外省（法属圭亚那 -53°、留尼汪 55°、马提尼克 -61°）把均值
    # 拉到 [-7.2, 34.9]（北非上空）；美国被阿拉斯加与夏威夷拉到 [-120.9, 48.4]
    # （加拿大西海岸）。直接用均值的话标签会飘到没有国土的地方。
    biggest = max(rings, key=lambda r: sum(1 for p in r if p))
    pts = [p for p in biggest if p]
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    center = [round((min(lons) + max(lons)) / 2, 2),
              round((min(lats) + max(lats)) / 2, 2)]
    # 同时存本土包围盒，前端用于点击拾取时的快速排除
    bbox = [round(min(lons), 2), round(min(lats), 2),
            round(max(lons), 2), round(max(lats), 2)]
    return rings, center, bbox, sum(1 for r in rings for p in r if p)


def main():
    if not os.path.exists(os.path.join(GEO, "_ne_110m_land.geojson")):
        print("缺少 geo/_ne_110m_land.geojson，先下载：")
        print("  curl -o geo/_ne_110m_land.geojson \\")
        print("    https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson")
        return 1

    land = collect_land()
    land_pts = sum(1 for r in land for p in r if p)
    print("陆地轮廓: %d 环 / %d 顶点" % (len(land), land_pts))

    countries = []
    for iso, name in COUNTRIES:
        try:
            rings, center, bbox, n = collect_country(iso)
        except FileNotFoundError:
            print("  %s 缺失 geo/%s.geojson，跳过" % (iso, iso.lower()))
            continue
        countries.append({"iso": iso, "name": name, "center": center,
                          "bbox": bbox, "rings": rings})
        print("  %-3s %-4s %2d 环 / %5d 顶点  标签 %s  bbox %s"
              % (iso, name, len(rings), n, center, bbox))

    out = {
        "generated": date.today().isoformat(),
        "note": "3D 地球专用。环内 null 表示跨经度 180° 的断点，前端绘线时需断开。",
        "precision": PRECISION,
        "tolerance": TOLERANCE,
        "land": land,
        "countries": countries,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    raw = os.path.getsize(OUT)
    total = land_pts + sum(1 for c in countries for r in c["rings"] for p in r if p)
    print("\n→ geo/globe.json  %.0f KB（%d 顶点，2 位小数，无 GeoJSON 冗余）" % (raw / 1024, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
