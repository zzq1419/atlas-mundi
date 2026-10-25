#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""寰宇图志 · 由 data/*.json 重算 data/index.json

用法：
    python scripts/sync_index.py

为什么需要它：
    collect.py 会在采集结束时顺手写一次 index.json，但那是按「当时」的字段算的。
    之后用 --geo 补边界、用 tts.py 补语音、用 optimize_images.py 换图，
    index 里的 modalities 和 status 就会与实际不符（中国补完边界后仍显示 4/5）。

    让 index.json 永远由档案反推，单一事实来源是 data/{iso}.json，避免手工对不上。
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

MOD_KEYS = ("image", "audio", "text", "coords", "geometry")


def modalities(rec):
    return {
        "image": bool(rec.get("landmark_images")),
        "audio": bool(rec.get("audio_url")),
        "text": bool(rec.get("summary_text")),
        "coords": bool(rec.get("centroid")),
        "geometry": bool(rec.get("geometry")),
    }


def main():
    idx_path = os.path.join(DATA, "index.json")
    with open(idx_path, encoding="utf-8") as f:
        idx = json.load(f)

    have = {}
    for fn in sorted(os.listdir(DATA)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        with open(os.path.join(DATA, fn), encoding="utf-8") as f:
            rec = json.load(f)
        # 配置类 JSON（landmarks.json 等）没有 iso_a2，不是国家档案，跳过
        if not rec.get("iso_a2"):
            continue
        have[rec["iso_a2"].upper()] = rec

    for c in idx.get("countries", []):
        iso = (c.get("iso_a2") or "").upper()
        rec = have.get(iso)
        if not rec:
            c["modalities"] = {k: False for k in MOD_KEYS}
            c["status"] = "placeholder"
            continue
        m = modalities(rec)
        c["modalities"] = m
        n = sum(1 for v in m.values() if v)
        c["status"] = "complete" if n == len(MOD_KEYS) else ("partial" if n else "placeholder")
        c["name_zh"] = rec.get("name_zh") or c.get("name_zh")
        c["name_en"] = rec.get("name_en") or c.get("name_en")
        c["name_local"] = rec.get("name_local") or rec.get("name_zh") or c.get("name_local")
        c["continent"] = rec.get("continent") or c.get("continent")
        c["capital"] = rec.get("capital") or c.get("capital")
        c["centroid"] = rec.get("centroid") or c.get("centroid")
        c["thumb"] = (rec["landmark_images"][0].get("thumb_url")
                      if rec.get("landmark_images") else None)
        c["lang_count"] = len(rec.get("languages") or [])
        c["audio_langs"] = [l.get("code") for l in (rec.get("languages") or [])
                            if l.get("audio_url")]

    # 有档案但 index 里没有的条目，补进去
    known = {(c.get("iso_a2") or "").upper() for c in idx.get("countries", [])}
    for iso, rec in have.items():
        if iso in known:
            continue
        m = modalities(rec)
        idx.setdefault("countries", []).append({
            "iso_a2": iso,
            "name_zh": rec.get("name_zh"),
            "name_en": rec.get("name_en"),
            "name_local": rec.get("name_local"),
            "continent": rec.get("continent"),
            "capital": rec.get("capital"),
            "centroid": rec.get("centroid"),
            "thumb": (rec["landmark_images"][0].get("thumb_url")
                      if rec.get("landmark_images") else None),
            "modalities": m,
            "status": "complete" if all(m.values()) else "partial",
        })

    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.write("\n")

    total = len(idx.get("countries", []))
    done = sum(1 for c in idx["countries"] if c.get("status") == "complete")
    print("data/index.json 已重算：%d 条，其中 %d 条 5/5 完整" % (total, done))
    for c in idx["countries"]:
        m = c["modalities"]
        bar = "".join("●" if m[k] else "○" for k in MOD_KEYS)
        print("  %-3s %-6s %s %d/5  %s" % (
            c["iso_a2"], c.get("name_zh") or "-", bar,
            sum(1 for v in m.values() if v), c.get("status")))


if __name__ == "__main__":
    main()
