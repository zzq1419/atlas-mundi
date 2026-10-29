#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成站点 logo 与 favicon（点阵球）。

设计来源：用户提供的截图 —— 纯黑底上一颗白色点阵球，边缘点密、中心点稀、
点径不一。这个分布不需要手工摆：球面上均匀采点再正交投影，边缘自然就密
（同样多的点被压到更小的投影面积里），所以用 Fibonacci 球面采样就能还原。

产物：
    assets/logo.svg     透明底，白色点阵球（放在左上角品牌区）
    assets/favicon.svg  黑底圆角方块 + 缩小的球（浏览器标签页）
"""

import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = math.pi * (3 - math.sqrt(5))


def sphere_points(n):
    """Fibonacci 球面均匀采样，只留前半球（z>0）。

    纯 Fibonacci 有个毛病：点在球面上排成一条条规则螺旋，投影到平面后能看出
    "同心螺旋纹"，跟原图那种散点感不一样。所以每个点的极角和方位角都加一点
    固定种子的抖动 —— 既打散纹路，又保证每次生成的图完全一致。"""
    rnd = random.Random(20261029)
    out = []
    for i in range(n):
        z = 1 - (2 * i + 1) / n + rnd.uniform(-0.012, 0.012)
        z = max(-1.0, min(1.0, z))
        r = math.sqrt(max(0.0, 1 - z * z))
        phi = i * GOLDEN + rnd.uniform(-0.22, 0.22)
        out.append((r * math.cos(phi), r * math.sin(phi), z))
    return out


def dots(n, cx, cy, radius, r_min, r_max, fill):
    """把前半球投影成 <circle>。点径随 z 变化：正面朝观察者的点大，贴边的点小。"""
    rows, k = [], 0
    for x, y, z in sphere_points(n):
        if z <= 0:
            continue
        px = cx + x * radius
        py = cy - y * radius
        # z 从 0（球缘）到 1（正中）
        rr = r_min + (r_max - r_min) * (z ** 0.85)
        rows.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s"/>' % (px, py, rr, fill))
        k += 1
    return rows, k


# 点数是按"实际显示尺寸"倒推的，不是越多越像。
# 第一版给了 1500 个采样点（前半球 750），在 64 的 viewBox 里平均间距只有 2px，
# 点径 0.55~2 —— 直接连成一张白饼，缩到 24px 就更认不出来了。
# 屏幕上这颗球只有 24~28px，点必须又少又大：前半球 200 来个点，
# 边缘自然密到粘连（这正是原图那圈亮环的成因），中心留得开。
def logo_svg():
    W = 64
    rows, k = dots(400, W / 2, W / 2, W / 2 - 4, 0.75, 1.95, "#ffffff")
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n%s\n</svg>\n'
            % (W, W, W, W, "\n".join(rows))), k


def favicon_svg():
    """标签页图标：黑底占大面积，球只占中间 56% —— 32px 下能看清是颗球，
    又留出足够的黑边让它在浅色标签栏里有个"块"的形状。"""
    W = 64
    pad = W * 0.22
    rows, k = dots(260, W / 2, W / 2, W / 2 - pad, 0.85, 2.1, "#f4f8ff")
    head = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n'
            '<rect width="%d" height="%d" rx="%d" fill="#05070c"/>\n'
            % (W, W, W, W, W, W, int(W * 0.22)))
    return head + "\n".join(rows) + "\n</svg>\n", k


def main():
    for name, fn in (("logo.svg", logo_svg), ("favicon.svg", favicon_svg)):
        svg, k = fn()
        path = os.path.join(ROOT, "assets", name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
        print("%-14s %6.1f KB  %d 个点" % (name, os.path.getsize(path) / 1024, k))


if __name__ == "__main__":
    main()
