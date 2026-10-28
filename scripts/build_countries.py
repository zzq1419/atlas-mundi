#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 Natural Earth 的 50m 国家图层拆成"每个国家一个文件"，并为全部国家生成元数据。

为什么拆：
  站点的定位是「所有国家」，但多模态档案（文本/影像/语音）只能一个个补。
  已经补好的放 data/{iso}.json；还没补的，用户点开时也应该看到一张像样的
  「基础档案」—— 名称、大洲、人口、中心坐标、国界轮廓，而不是一句
  "档案未就绪"。基础档案的数据全部来自 Natural Earth，拆成单文件按需取，
  避免首屏拉一个 3MB 的全世界边界。

产物：
  geo/meta.json        {ISO: {n, en, cont, pop, lon, lat}}   约 20KB，进首屏
  geo/c{0..7}.json     8 个分片，每个是 {ISO: FeatureCollection}，
                       记录格式与 geo/cn.geojson 一致（MultiPolygon），
                       所以详情页的轮廓渲染不用改。
为什么分片而不是一国一个文件：一国的几何只有 5KB，看起来"按需取"最省，
但 224 个文件意味着部署时要上传/提交 224 次，静态托管的构建也慢；
分片后每个 ~130KB（gzip 约 30KB），一次点击只多几十毫秒，换部署的确定性。
分片用 ISO 的字符和取模，前后端各算一次，不需要额外索引。
"""
import json
import os
import sys

# 控制台可能是 cp936（Windows cmd 默认），打不出的字符用 ? 代替，别让整段崩掉。
# 之前 collect.py 在连不上某个站时打印一个 ✗ 就 UnicodeEncodeError 退出，
# 看起来像"采集失败"，其实连抓取都还没开始。
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from build_labels import SHORT  # 同一个中文简称表，避免两处漂移

NE = os.path.join(ROOT, "geo", "_ne_50m_countries.geojson")
OUT_META = os.path.join(ROOT, "geo", "meta.json")
BUCKETS = 8


def bucket(iso):
    """与前端 geoBucket() 完全一致：ISO 各字符 code 之和取模。"""
    return sum(ord(ch) for ch in iso) % BUCKETS

CONT = {
    "Asia": "亚洲",
    "Europe": "欧洲",
    "Africa": "非洲",
    "North America": "北美洲",
    "South America": "南美洲",
    "Oceania": "大洋洲",
    "Antarctica": "南极洲",
    "Seven seas (open ocean)": "公海",
}

# 简化参数：50m 图层本来就粗，这里只做"去重 + 抽稀 + 三位小数"
MIN_STEP = 0.06      # 相邻点小于这个经纬度距离就丢掉（≈6km）
MAX_POINTS = 700     # 单个环的上限，超了按等间隔抽
ROUND = 3


def ring_simplify(ring):
    out = []
    for pt in ring:
        x, y = round(float(pt[0]), ROUND), round(float(pt[1]), ROUND)
        if out and abs(x - out[-1][0]) < MIN_STEP and abs(y - out[-1][1]) < MIN_STEP:
            continue
        out.append([x, y])
    if len(out) > MAX_POINTS:
        step = len(out) / float(MAX_POINTS)
        out = [out[int(i * step)] for i in range(MAX_POINTS)]
    if len(out) < 4:
        return None
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def main():
    with open(NE, encoding="utf-8") as f:
        src = json.load(f)

    meta = {}
    chunks = [{} for _ in range(BUCKETS)]
    written = 0
    total_bytes = 0
    skipped = []

    # 同一个 ISO 在 NE 里可能有多个要素：AU 就有 Australia / Indian Ocean Ter. /
    # Ashmore and Cartier 三个，后写的会把先写的覆盖掉 —— 实测 meta["AU"] 变成了
    # "澳屬印度洋領地"（人口 2387），澳大利亚本身反而没了。规则：同 ISO 留人口最多的。
    feats = src.get("features", [])
    best = {}
    for idx, feat in enumerate(feats):
        q = feat.get("properties", {}) or {}
        code = (q.get("ISO_A2") or "").upper()
        if len(code) != 2:
            code = (q.get("ISO_A2_EH") or "").upper()
        if len(code) != 2:
            continue
        pop = int(q.get("POP_EST") or 0)
        if code not in best or pop > best[code][0]:
            best[code] = (pop, idx)

    for idx, feat in enumerate(feats):
        p = feat.get("properties", {})
        iso = (p.get("ISO_A2") or "").upper()
        if len(iso) != 2:
            iso = (p.get("ISO_A2_EH") or "").upper()
        if len(iso) != 2:
            skipped.append(p.get("NAME"))
            continue
        if best.get(iso) and best[iso][1] != idx:
            continue                     # 同 ISO 的非主要素（属地/离岛）跳过

        name_zh = p.get("NAME_ZH") or p.get("NAME") or iso
        name_zh = SHORT.get(name_zh, name_zh)

        g = feat.get("geometry") or {}
        polys = g.get("type") == "Polygon" and [g["coordinates"]] or \
            (g.get("type") == "MultiPolygon" and g["coordinates"] or [])

        out_polys = []
        minx = miny = 1e9
        maxx = maxy = -1e9
        for poly in polys:
            rings = []
            for ring in poly:
                r = ring_simplify(ring)
                if not r:
                    continue
                rings.append(r)
                for x, y in r:
                    minx, maxx = min(minx, x), max(maxx, x)
                    miny, maxy = min(miny, y), max(maxy, y)
            if rings:
                out_polys.append(rings)

        if not out_polys:
            skipped.append(p.get("NAME"))
            continue

        gj = {
            "type": "FeatureCollection",
            "name": name_zh,
            "features": [{
                "type": "Feature",
                "properties": {"name": name_zh, "iso_a2": iso},
                "geometry": {"type": "MultiPolygon", "coordinates": out_polys},
            }],
        }
        gj["iso"] = iso
        chunks[bucket(iso)][iso] = gj
        written += 1

        try:
            pop = int(p.get("POP_EST") or 0)
        except (TypeError, ValueError):
            pop = 0
        meta[iso] = {
            "n": name_zh,
            "en": p.get("NAME") or iso,
            "cont": CONT.get(p.get("CONTINENT") or "", ""),
            "pop": pop,
            "lon": round(float(p.get("LABEL_X") or 0), 2),
            "lat": round(float(p.get("LABEL_Y") or 0), 2),
        }

    with open(OUT_META, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(meta, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    for i, ch in enumerate(chunks):
        fp = os.path.join(ROOT, "geo", "c%d.json" % i) if False else \
            os.path.join(ROOT, "geo", "c%d.json" % i)
        with open(fp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(ch, ensure_ascii=False, separators=(",", ":")))
        total_bytes += os.path.getsize(fp)
        print("  c%d.json  %3d 国  %6.1f KB" % (i, len(ch), os.path.getsize(fp) / 1024.0))

    print("分片合计 %.1f MB，共 %d 个国家" % (total_bytes / 1048576.0, written))
    print("meta.json %.1f KB" % (os.path.getsize(OUT_META) / 1024.0))
    if skipped:
        print("跳过 %d 个（无 ISO 或几何为空）：%s" % (len(skipped), "、".join(skipped[:6])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
