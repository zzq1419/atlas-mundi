#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""国界环的抽稀（Douglas-Peucker）—— build_countries 与 build_geo 共用。

为什么单独一个文件：
    球面国界分片（geo/c*.json）和详情面板的轮廓（data/{iso}.json 的 geometry）
    是同一套边界的两种产物。抽稀参数写两处，迟早会一边细一边粗 ——
    球上看着是圆的、面板里却是折线。规则只留一份。

为什么是 DP 不是"相邻点太近就丢"：
    按固定步长丢点会把拐角一起抹掉。江苏海岸那种"缓弧 + 小湾"的地方，
    6km 步长能把它抹成三段直线，叠在 8K 卫星影像旁边一眼就看出形状不对。
    DP 只在"偏离弦线超过容差"时才留点，同样的点数能撑住形状。
"""

TOL = 0.006          # 度，约 650m。8K 贴图一像素约 0.044°，这个精度肉眼看不出
MAX_POINTS = 8000    # 单环上限，超了才等间隔抽（南极洲、俄罗斯那种超长环）
ROUND = 3


def dp(points, tol=TOL):
    """Douglas-Peucker。迭代实现 —— 递归版在 3 万点的环上会爆栈。"""
    n = len(points)
    if n < 3:
        return points
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    tol2 = tol * tol
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            if den > 0:
                t = ((px - ax) * dx + (py - ay) * dy) / den
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                ex, ey = ax + t * dx, ay + t * dy
            else:
                ex, ey = ax, ay
            d2 = (px - ex) ** 2 + (py - ey) ** 2
            if d2 > best:
                best, bi = d2, i
        if best > tol2 and bi > 0:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    return [points[i] for i in range(n) if keep[i]]


def simplify_ring(ring, tol=TOL, max_points=MAX_POINTS):
    """去重 → DP 抽稀 → 限长 → 闭合。少于 4 点返回 None（画不成面）。"""
    pts = []
    for pt in ring:
        x, y = round(float(pt[0]), ROUND), round(float(pt[1]), ROUND)
        if pts and pts[-1] == [x, y]:
            continue
        pts.append([x, y])
    pts = dp(pts, tol)
    if len(pts) > max_points:
        step = len(pts) / float(max_points)
        pts = [pts[int(i * step)] for i in range(max_points)]
    if len(pts) < 4:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts
