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
    # 台湾、香港、澳门是中国的一部分，标注按「中国XX」书写；
    # Natural Earth 把它们当成独立要素（台湾的 NAME_ZH 甚至还写着旧政权名），
    # 这里必须改正 —— 地球上的国界数据已经把它们并进中国了，标注不能自相矛盾。
    "中华民国": "中国台湾",
    "台湾": "中国台湾",
    "香港": "中国香港",
    "澳门": "中国澳门",
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



# ---------------------------------------------------------------------------
# 岛屿 / 湖泊 / 海峡：Natural Earth 的国家图层里没有这些，逐条手写。
# 只要"重要的、缩放拉近之后才需要看的"—— 几十条足矣，多了必然糊。
# 第四个数字是起始缩放级（NE zoom，越大越晚出现）。
# 远离本土的岛在后面用括号标国属：关岛（美国）、新喀里多尼亚（法国）。
# 有主权争议的一律不标国属（福克兰/马尔维纳斯这类直接不收）。
# ---------------------------------------------------------------------------
ISLANDS = [
    ("夏威夷（美国）", -155.5, 19.6, 3.2),
    ("纽芬兰（加拿大）", -56.1, 48.6, 3.4),
    ("巴芬岛（加拿大）", -70.0, 68.0, 3.6),
    ("斯瓦尔巴（挪威）", 15.6, 78.2, 3.6),
    ("法罗群岛（丹麦）", -6.9, 62.0, 3.8),
    ("百慕大（英国）", -64.8, 32.3, 3.8),
    ("亚速尔群岛（葡萄牙）", -25.5, 37.8, 3.8),
    ("加那利群岛（西班牙）", -16.0, 28.2, 3.8),
    ("留尼汪（法国）", 55.5, -21.1, 3.8),
    ("新喀里多尼亚（法国）", 165.6, -21.3, 3.8),
    ("复活节岛（智利）", -109.3, -27.1, 4.2),
    ("迪戈加西亚（英属）", 72.4, -7.3, 4.4),
    ("关岛（美国）", 144.8, 13.4, 3.6),
    ("塞班岛（美国）", 145.75, 15.2, 4.0),
    ("中途岛（美国）", -177.4, 28.2, 4.4),
    ("冲绳岛（日本）", 127.9, 26.4, 4.0),
    ("库页岛（俄罗斯）", 143.0, 51.0, 3.8),
    ("海南岛（中国）", 109.8, 19.2, 3.6),
    ("加里曼丹岛", 113.0, 0.5, 3.4),
    ("苏门答腊岛（印尼）", 102.0, -1.0, 3.4),
    ("爪哇岛（印尼）", 110.5, -7.3, 3.6),
    ("新几内亚岛", 141.0, -5.0, 3.4),
    ("吕宋岛（菲律宾）", 121.0, 16.0, 3.8),
    ("棉兰老岛（菲律宾）", 122.5, 7.5, 4.0),
    ("火地岛（阿根廷·智利）", -68.0, -54.0, 3.6),
]

LAKES = [
    ("里海", 50.5, 42.0, 2.8),
    ("贝加尔湖", 108.0, 53.5, 3.2),
    ("苏必利尔湖", -87.8, 47.6, 3.2),
    ("维多利亚湖", 33.0, -1.0, 3.4),
    ("拉多加湖", 31.5, 61.0, 3.6),
    ("坦噶尼喀湖", 29.6, -6.0, 3.6),
    ("密歇根湖", -87.0, 44.0, 3.6),
    ("的的喀喀湖", -69.3, -15.8, 3.8),
    ("青海湖", 100.2, 36.9, 3.8),
    ("马拉维湖", 34.5, -12.0, 3.8),
    ("死海", 35.5, 31.5, 4.0),
]

STRAITS = [
    ("马六甲海峡", 100.5, 2.5, 3.4),
    ("白令海峡", -169.0, 65.8, 3.6),
    ("德雷克海峡", -63.0, -58.0, 3.6),
    ("英吉利海峡", 0.5, 50.2, 3.8),
    ("莫桑比克海峡", 41.0, -18.0, 3.8),
    ("直布罗陀海峡", -5.6, 35.95, 3.8),
    ("台湾海峡", 119.5, 24.5, 4.0),
    ("霍尔木兹海峡", 56.4, 26.6, 4.0),
    ("曼德海峡", 43.4, 12.6, 4.2),
    ("朝鲜海峡", 129.0, 34.0, 4.2),
    ("麦哲伦海峡", -70.5, -53.5, 4.2),
    ("苏伊士运河", 32.3, 30.5, 4.2),
    ("巴拿马运河", -79.6, 9.1, 4.2),
    ("巴士海峡", 121.0, 21.0, 4.4),
    ("博斯普鲁斯海峡", 29.0, 41.1, 4.4),
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

    feats = []
    for name, lon, lat, z in ISLANDS:
        feats.append({"n": name, "lon": lon, "lat": lat, "z": z, "k": "i"})
    for name, lon, lat, z in LAKES:
        feats.append({"n": name, "lon": lon, "lat": lat, "z": z, "k": "l"})
    for name, lon, lat, z in STRAITS:
        feats.append({"n": name, "lon": lon, "lat": lat, "z": z, "k": "s"})
    feats.sort(key=lambda f: f["z"])
    print("岛屿/湖泊/海峡 %d 条（岛 %d · 湖 %d · 海峡 %d）"
          % (len(feats), len(ISLANDS), len(LAKES), len(STRAITS)))

    out = {
        "note": "锚点/缩放级别取自 Natural Earth LABEL_X/LABEL_Y/MIN_LABEL/LABELRANK",
        "features": feats,
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
