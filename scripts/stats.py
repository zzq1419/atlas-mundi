#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""寰宇图志 · 数据集统计（给 PPT 与报告用）

用法：
    python scripts/stats.py            # 打印到控制台
    python scripts/stats.py --json     # 输出 JSON，便于贴到别处

交接文档第 14 节要求：答辩 PPT 必须有可量化指标 —— 覆盖国家数、数据条数、图片数、
音频数、数据源数、字段完整率、融合成功率、平均加载耗时。
数字一律从产物反推，不手写。
"""

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# 交付要求的 13 个标准字段（geometry 只在阶段 D 用，但要求已采集）
FIELDS = ["qid", "iso_a2", "iso_a3", "name_zh", "name_en", "capital", "continent",
          "centroid", "languages", "landmark_images", "image_license",
          "summary_text", "custom_text", "audio_url", "geometry"]


def human(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return "%.0f %s" % (n, unit) if unit != "KB" else "%.0f KB" % n
        n /= 1024.0
    return "%d B" % n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    recs = []
    for fn in sorted(os.listdir(DATA)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        with open(os.path.join(DATA, fn), encoding="utf-8") as f:
            recs.append(json.load(f))

    idx = {}
    ip = os.path.join(DATA, "index.json")
    if os.path.exists(ip):
        with open(ip, encoding="utf-8") as f:
            idx = json.load(f)

    n_c = len(recs)
    filled = sum(1 for r in recs for k in FIELDS if r.get(k))
    total_cells = n_c * len(FIELDS)

    images = [im for r in recs for im in (r.get("landmark_images") or [])]
    audios = [l for r in recs for l in (r.get("languages") or []) if l.get("audio_url")]
    langs = [l for r in recs for l in (r.get("languages") or [])]

    # 素材体积（只统计被 JSON 引用的文件）
    def size_of(rel):
        p = os.path.join(ROOT, rel)
        return os.path.getsize(p) if os.path.exists(p) else 0

    img_bytes = sum(size_of(im["url"]) for im in images)
    thumb_bytes = sum(size_of(im.get("thumb_url") or im["url"]) for im in images)
    aud_bytes = sum(size_of(l["audio_url"]) for l in audios)
    geo_bytes = sum(size_of(r["geometry"]) for r in recs if r.get("geometry"))

    # 只统计真实的机采数据源。manual（人工撰写）不算数据源，单列。
    # 不要把没用过的源写进来 —— 报告里写「用了 LLM 改写」而实际没调，是造假。
    sources, manual_fields = set(), 0
    for r in recs:
        for s in (r.get("sources") or []):
            src = {"wikipedia_rest": "wikipedia"}.get(s.get("source"), s.get("source"))
            if src == "manual":
                manual_fields += 1
            elif src:
                sources.add(src)
    if any(r.get("summary_source", {}).get("source") == "wikipedia_extracts" for r in recs):
        sources.add("wikipedia")
    if any(l.get("audio_source", "").startswith("tts") for l in langs):
        sources.add("tts")
    sources.discard(None)

    # 融合成功率：index 里 status=complete 的比例
    cs = idx.get("countries") or []
    complete = sum(1 for c in cs if c.get("status") == "complete")

    stats = {
        "国家/地区数": n_c,
        "字段完整率": "%d/%d = %.1f%%" % (filled, total_cells, filled * 100.0 / total_cells),
        "地标图片数": len(images),
        "语音条数": len(audios),
        "语言条目数": len(langs),
        "机采数据源数": len(sources),
        "人工撰写字段数": manual_fields,
        "数据源清单": sorted(x for x in sources if x),
        "5/5 完整国家数": "%d/%d" % (complete, len(cs)),
        "图片体积(详情)": human(img_bytes),
        "图片体积(缩略)": human(thumb_bytes),
        "音频体积": human(aud_bytes),
        "边界体积": human(geo_bytes),
        "字段清单": FIELDS,
    }

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    print("=" * 52)
    print("寰宇图志 · 数据集统计")
    print("=" * 52)
    for k, v in stats.items():
        if k == "字段清单":
            continue
        print("  %-18s %s" % (k, v))
    print("-" * 52)
    print("  %-6s %-6s %s" % ("ISO", "名称", "字段缺口"))
    for r in recs:
        miss = [k for k in FIELDS if not r.get(k)]
        print("  %-6s %-6s %s" % (r.get("iso_a2"), r.get("name_zh"),
                                  "无" if not miss else "、".join(miss)))


if __name__ == "__main__":
    main()
