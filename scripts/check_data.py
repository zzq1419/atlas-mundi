#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据集完整性检查（CI 门禁）

用法：
    python scripts/check_data.py          # 有问题退出码 1
    python scripts/check_data.py --warn   # 只告警不失败

检查项：
    1. data/*.json 都能解析，且带 iso_a2（排除 landmarks.json 这类配置）
    2. 15 个标准字段都在
    3. landmark_images / languages 引用的素材文件真实存在且非空
    4. geo/*.geojson 是合法 FeatureCollection + MultiPolygon
    5. data/index.json 的 modalities 与档案一致（防止补了图/音忘了同步）
    6. 国界合并规则：中国必须已并入中国台湾/中国香港/中国澳门

第 6 条是硬性合规要求，不是风格问题。
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


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import geo_rules  # noqa: E402

DATA = os.path.join(ROOT, "data")
FIELDS = ["qid", "iso_a2", "iso_a3", "name_zh", "name_en", "capital", "continent",
          "centroid", "languages", "landmark_images", "image_license",
          "summary_text", "custom_text", "audio_url", "geometry"]

problems, warnings = [], []


def err(msg):
    problems.append(msg)


def warn(msg):
    warnings.append(msg)


def load_countries():
    out = {}
    for fn in sorted(os.listdir(DATA)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        p = os.path.join(DATA, fn)
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception as e:
            err("%s 解析失败：%s" % (fn, e))
            continue
        if not rec.get("iso_a2"):
            continue          # 配置文件
        out[rec["iso_a2"].upper()] = rec
    if not out:
        err("data/ 下没有任何国家档案")
    return out


def check_fields(iso, rec):
    missing = [k for k in FIELDS if not rec.get(k)]
    if missing:
        err("%s 缺字段：%s" % (iso, "、".join(missing)))


def check_asset(iso, rel, kind):
    if not rel:
        err("%s 的 %s 路径为空" % (iso, kind))
        return
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        err("%s 的 %s 文件不存在：%s" % (iso, kind, rel))
    elif os.path.getsize(p) < 512:
        err("%s 的 %s 文件过小（%d B）：%s" % (iso, kind, os.path.getsize(p), rel))


def check_geometry(iso, rec):
    rel = rec.get("geometry")
    if not rel:
        return
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        err("%s 的边界文件不存在：%s" % (iso, rel))
        return
    try:
        with open(p, encoding="utf-8") as f:
            gj = json.load(f)
    except Exception as e:
        err("%s 边界解析失败：%s" % (iso, e))
        return
    if gj.get("type") != "FeatureCollection" or not gj.get("features"):
        err("%s 边界不是合法 FeatureCollection" % iso)
        return
    g = gj["features"][0].get("geometry") or {}
    if g.get("type") != "MultiPolygon":
        err("%s 边界 geometry 不是 MultiPolygon（是 %s）" % (iso, g.get("type")))
        return
    n = sum(len(r) for poly in g["coordinates"] for r in poly)
    if n < 3:
        err("%s 边界顶点数过少：%d" % (iso, n))

    # 合规：合并表里要求的要素必须真的并进去了
    need = geo_rules.MERGE_INTO.get(iso, [])
    merged = (gj["features"][0].get("properties") or {}).get("_merged_iso") or []
    lost = [c for c in need if c not in merged]
    if lost:
        err("%s 版图缺少必须并入的要素：%s（属错绘）" % (iso, "、".join(lost)))


def check_index(countries):
    p = os.path.join(DATA, "index.json")
    if not os.path.exists(p):
        err("缺少 data/index.json")
        return
    with open(p, encoding="utf-8") as f:
        idx = json.load(f)
    listed = {(c.get("iso_a2") or "").upper(): c for c in idx.get("countries", [])}

    for iso, rec in countries.items():
        if iso not in listed:
            warn("%s 有档案但没进 index.json" % iso)
            continue
        want = {
            "image": bool(rec.get("landmark_images")),
            "audio": bool(rec.get("audio_url")),
            "text": bool(rec.get("summary_text")),
            "coords": bool(rec.get("centroid")),
            "geometry": bool(rec.get("geometry")),
        }
        got = listed[iso].get("modalities") or {}
        diff = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
        if diff:
            err("%s 的 index.modalities 与档案不一致：%s（跑 sync_index.py）" % (iso, diff))

    for iso in listed:
        if iso not in countries:
            err("index.json 里有 %s，但 data/ 下没有对应档案" % iso)


def check_iso_hygiene(countries):
    bad = [iso for iso in countries if iso in geo_rules.NEVER_AS_COUNTRY]
    if bad:
        err("这些 ISO 码不应作为独立国家出现（已并入父级版图）：%s" % "、".join(bad))


def main():
    warn_only = "--warn" in sys.argv
    countries = load_countries()

    for iso, rec in countries.items():
        check_fields(iso, rec)
        for i, im in enumerate(rec.get("landmark_images") or [], 1):
            check_asset(iso, im.get("url"), "图片%d" % i)
            check_asset(iso, im.get("thumb_url"), "缩略图%d" % i)
            if not im.get("license"):
                warn("%s 图片%d 无授权字段（%s）" % (iso, i, im.get("title", "")))
        for l in rec.get("languages") or []:
            if l.get("audio_url"):
                check_asset(iso, l["audio_url"], "语音(%s)" % l.get("code"))
        check_geometry(iso, rec)

    check_index(countries)
    check_iso_hygiene(countries)

    print("检查 %d 个国家/地区" % len(countries))
    if warnings:
        print("\n告警 %d 条：" % len(warnings))
        for w in warnings:
            print("  · " + w)
    if problems:
        print("\n问题 %d 条：" % len(problems))
        for p in problems:
            print("  [x] " + p)
        if not warn_only:
            sys.exit(1)
    else:
        print("\n[ok] 全部通过")


if __name__ == "__main__":
    main()
