#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 Natural Earth 50m 生成各国 geo/{iso}.geojson（含主权归属合并）

用法：
    python scripts/build_geo.py            # 重新生成 data/ 下所有国家的边界
    python scripts/build_geo.py CN FR US
    python scripts/build_geo.py CN --check # 只报告多边形/顶点数，不写文件

前置：geo/_ne_50m_countries.geojson 已存在
（由 collect.py --geo 首次下载，或手动 curl 下来放到该路径）

为什么不直接切一个 feature 就行：
    Natural Earth 把中国台湾、中国香港、中国澳门画成独立要素。只取 CN 那条，
    画出来的中国地图东岸到 122°E 就断了，台湾是缺的 —— 这是错绘。
    合并规则写在 geo_rules.MERGE_INTO 里，采集与重绘共用一份。
"""

import argparse
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


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import geo_rules  # noqa: E402

NE = os.path.join(ROOT, "geo", "_ne_50m_countries.geojson")


def codes_of(props):
    return {str(props.get(k) or "").upper()
            for k in ("ISO_A2", "ISO_A2_EH", "WB_A2")} - {""}


def polys_of(feature):
    g = feature["geometry"]
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    if g["type"] == "MultiPolygon":
        return g["coordinates"]
    return []


def load_ne():
    if not os.path.exists(NE):
        raise SystemExit("缺少 %s，请先跑 collect.py --geo 或手动下载" % os.path.relpath(NE, ROOT))
    with open(NE, encoding="utf-8") as f:
        return json.load(f)["features"]


def build(features, iso):
    iso = iso.upper()
    merge = geo_rules.MERGE_INTO.get(iso, [])
    main, extra = None, []
    for feat in features:
        cs = codes_of(feat["properties"])
        if main is None and iso in cs:
            main = feat
        elif merge and (cs & set(merge)):
            extra.append((sorted(cs & set(merge))[0], feat))
    if main is None:
        return None, "Natural Earth 中没有 ISO_A2=%s" % iso

    polys = list(polys_of(main))
    merged = []
    for code, feat in extra:
        polys.extend(polys_of(feat))
        merged.append(code)

    props = dict(main["properties"])
    props["NAME_ZH"] = geo_rules.DISPLAY_NAME.get(iso, props.get("NAME_ZH"))
    props["_merged_iso"] = merged
    props["_compliance"] = geo_rules.COMPLIANCE_NOTE

    out_feat = {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "MultiPolygon", "coordinates": polys},
    }
    fc = {"type": "FeatureCollection", "features": [out_feat]}

    verts = sum(len(r) for poly in polys for r in poly)
    stats = {"rings": sum(len(p) for p in polys), "vertices": verts,
             "merged": merged, "polygons": len(polys)}
    return (fc, stats), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("isos", nargs="*")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    features = load_ne()
    isos = [x.upper() for x in args.isos]
    if not isos:
        d = os.path.join(ROOT, "data")
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json") or fn in ("index.json", "landmarks.json"):
                continue
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                rec = json.load(f)
            if rec.get("iso_a2"):
                isos.append(rec["iso_a2"].upper())

    for iso in isos:
        res, err = build(features, iso)
        if err:
            print("  ! %s %s" % (iso, err))
            continue
        fc, st = res
        if iso in geo_rules.NEVER_AS_COUNTRY:
            print("  ! %s 在合并表里，不应单独成图，跳过" % iso)
            continue
        path = os.path.join(ROOT, "geo", "%s.geojson" % iso.lower())
        size = 0
        if not args.check:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(fc, f, ensure_ascii=False)
            size = os.path.getsize(path)
        print("  [ok] %-3s 多边形 %3d  环 %3d  顶点 %5d  合并 %s%s" % (
            iso, st["polygons"], st["rings"], st["vertices"],
            "、".join(st["merged"]) or "无",
            ("  %.0f KB" % (size / 1024)) if size else ""))


if __name__ == "__main__":
    main()
