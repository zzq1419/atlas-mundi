#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成球面地图标注数据 geo/labels.json。

数据来源：Natural Earth 1:50m Admin 0 Countries（公有领域）。
关键是用它自带的**制图字段**，而不是自己猜位置：

  LABEL_X / LABEL_Y  制图师放标签的锚点（不是几何中心 —— 挪威的几何中心在海上）
  MIN_LABEL          该标签从第几级缩放开始出现（Natural Earth 的 zoom 级别）
  LABELRANK          重要度，1 最高。碰撞时先保小的

这正好是「像谷歌地图一样按缩放显示地名」该有的输入，不用自己编规则。
大洲与大洋没有现成数据，用手写锚点（放在比较空的海面/大陆中部，避开国名）。

用法：
    python scripts/build_labels.py
输出：geo/labels.json（约 12KB）
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "geo", "_ne_50m_countries.geojson")
OUT = os.path.join(ROOT, "geo", "labels.json")

# 站内已收录、可点开档案的国家：不参与缩放过滤，永远显示且优先级最高
FEATURED = {"CN", "FR", "US"}

# 地图上不写全称。Natural Earth 的中文名是官方全称，世界缩放下太长
SHORT = {
    "中华人民共和国": "中国",
    "大韩民国": "韩国",
    "朝鲜民主主义人民共和国": "朝鲜",
    "伊朗伊斯兰共和国": "伊朗",
    "阿拉伯联合酋长国": "阿联酋",
    "阿拉伯叙利亚共和国": "叙利亚",
    "老挝人民民主共和国": "老挝",
    "委内瑞拉玻利瓦尔共和国": "委内瑞拉",
    "玻利维亚多民族国": "玻利维亚",
    "坦桑尼亚联合共和国": "坦桑尼亚",
    "刚果民主共和国": "刚果（金）",
    "多米尼加共和国": "多米尼加",
    "捷克共和国": "捷克",
    "中非共和国": "中非",
    "大不列颠及北爱尔兰联合王国": "英国",
    "俄罗斯联邦": "俄罗斯",
    "美利坚合众国": "美国",
}

# 大洲与大洋：锚点选在大陆中部或空海面，避开国名密集区
CONTINENTS = [
    ("亚洲", 88, 44, 0.0, 0),
    ("欧洲", 16, 53, 0.0, 1),
    ("非洲", 20, 3, 0.0, 2),
    ("北美洲", -101, 46, 0.0, 3),
    ("南美洲", -60, -14, 0.0, 4),
    ("大洋洲", 134, -25, 0.0, 5),
    ("南极洲", 0, -78, 0.0, 6),
]

OCEANS = [
    ("太平洋", -152, 8, 0.0, 10),
    ("大西洋", -32, 22, 0.0, 11),
    ("印度洋", 78, -26, 0.0, 12),
    ("北冰洋", -20, 84, 0.0, 13),
    ("南大洋", 20, -58, 0.0, 14),
]


def main() -> int:
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)

    countries = []
    for feat in data["features"]:
        p = feat["properties"]
        lon, lat = p.get("LABEL_X"), p.get("LABEL_Y")
        if lon is None or lat is None:
            continue
        name = p.get("NAME_ZH") or p.get("NAME")
        if not name:
            continue
        # France / Norway / Kosovo 的 ISO_A2 是 -99，要用 ISO_A2_EH
        iso = (p.get("ISO_A2") or "").upper()
        if len(iso) != 2:
            iso = (p.get("ISO_A2_EH") or "").upper()
        name = SHORT.get(name, name)
        countries.append({
            "n": name,
            "lon": round(float(lon), 2),
            "lat": round(float(lat), 2),
            # MIN_LABEL 是 NE 的 zoom 级；LABELRANK 越小越重要
            "z": float(p.get("MIN_LABEL") or 5),
            "r": int(p.get("LABELRANK") or 6),
            "iso": iso if iso in FEATURED else "",
        })

    countries.sort(key=lambda c: (c["r"], c["z"], -len(c["n"])))
    print("国家标注 %d 条（其中站内可点 %d 条）"
          % (len(countries), sum(1 for c in countries if c["iso"])))

    out = {
        "note": "锚点/缩放级别取自 Natural Earth LABEL_X/LABEL_Y/MIN_LABEL/LABELRANK",
        "countries": countries,
        "continents": [{"n": n, "lon": x, "lat": y, "z": z, "r": r}
                       for (n, x, y, z, r) in CONTINENTS],
        "oceans": [{"n": n, "lon": x, "lat": y, "z": z, "r": r}
                   for (n, x, y, z, r) in OCEANS],
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("→ %s  %.1f KB" % (os.path.basename(OUT), os.path.getsize(OUT) / 1024))

    # 抽查几个：世界级缩放该看到的大国
    print("  最小 MIN_LABEL：", sorted({c["z"] for c in countries})[:6])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
