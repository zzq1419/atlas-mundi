# -*- coding: utf-8 -*-
"""把 geo/{iso}.geojson 的实测统计写回 data/{iso}.json。

为什么需要：档案里 geometry 只是一个路径，面板上的「边界」一行写的是
「Natural Earth 10m · N 顶点」。重新生成边界后如果不回填，
显示的顶点数就是上一版的 —— 数字对不上，等于又一处说谎。

用法：python scripts/sync_geo_stats.py            # 所有带 geometry 的档案
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    n = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "*.json"))):
        base = os.path.basename(path)
        if base.startswith("_") or base in ("index.json", "landmarks.json", "search.json"):
            continue
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        rel = rec.get("geometry")
        if not isinstance(rel, str) or not rel:
            continue
        gp = os.path.join(ROOT, rel)
        if not os.path.exists(gp):
            print("  ! %s 缺 %s" % (rec.get("iso_a2"), rel))
            continue
        gj = json.load(open(gp, encoding="utf-8"))
        polys, rings, verts = 0, 0, 0
        for feat in gj.get("features", []):
            g = feat.get("geometry") or {}
            ps = [g["coordinates"]] if g.get("type") == "Polygon" else (g.get("coordinates") or [])
            for poly in ps:
                polys += 1
                for r in poly:
                    rings += 1
                    verts += len(r)
        before = (rec.get("geometry_stats") or {}).get("vertices")
        rec["geometry_stats"] = {
            "rings": rings,
            "vertices": verts,
            "polygons": polys,
            "merged": (rec.get("geometry_stats") or {}).get("merged") or [],
            "bytes": os.path.getsize(gp),
        }
        rec["geometry_status"] = "naturalearth_10m_merged"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("  %-3s %-8s %5d → %5d 顶点" % (rec.get("iso_a2"), rec.get("name_zh"),
                                             before or 0, verts))
        n += 1
    print("回填 %d 个档案" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
