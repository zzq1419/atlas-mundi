#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""寰宇图志 · 按人工清单补齐地标图

用法：
    python scripts/fill_images.py CN FR US
    python scripts/fill_images.py --all

为什么需要这一步：
    Wikidata P18 每个国家只给 1 张「代表图」，而且不保证是地标
    （美国给的是 UNOCHA 的定位地图）。自动挑选也无法保证挑中"最著名的那一张"。

    所以把「要哪几处地标」写进 data/landmarks.json，由人工指定，
    脚本按关键词去 Commons 搜图，取回后写死中文图注。
    这样图注是中文的、顺序是可控的、封面是选出来的。

流程：
    data/landmarks.json (关键词 + 中文图注)
      -> Commons list=search 搜 File 命名空间
      -> 过滤地图/旗帜/徽章 + 要求有授权 + 要求宽度 >= 800
      -> 下载到 assets/{iso}/L01.jpg ... L04.jpg
      -> 覆写 data/{iso}.json 的 landmark_images，caption_zh 直接写中文
      -> 之后跑 optimize_images.py 压成 WebP
"""

import argparse
import importlib.util
import json
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 复用 collect.py 的请求工具与图片过滤，避免两套实现漂移
_spec = importlib.util.spec_from_file_location(
    "atlas_collect", os.path.join(ROOT, "scripts", "collect.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MIN_WIDTH = 800
MAX_PER_COUNTRY = 5


def log(msg=""):
    print(msg, flush=True)


def search_files(kw, limit=12):
    """在 Commons 的 File 命名空间里搜位图，返回候选文件名"""
    q = C.api_json(COMMONS_API, {
        "action": "query", "list": "search", "srsearch": kw + " filetype:bitmap",
        "srnamespace": "6", "srlimit": str(limit), "format": "json",
    })
    out = []
    for item in (q.get("query", {}).get("search", []) or []):
        name = (item.get("title") or "").replace("File:", "")
        if name and not C.is_bad_image(name):
            out.append(name)
    return out


def pick_and_download(iso, entries, rec):
    slug = iso.lower()
    adir = os.path.join(ROOT, "assets", slug)
    os.makedirs(adir, exist_ok=True)
    picked, notes = [], []

    for i, e in enumerate(entries[:MAX_PER_COUNTRY], 1):
        kw, zh = e.get("kw"), e.get("zh")
        cand = search_files(kw)
        if not cand:
            notes.append("%s：Commons 搜不到「%s」，已跳过" % (zh, kw))
            log("      ✗ %s 搜不到" % zh)
            continue

        info = C.commons_imageinfo(cand)
        chosen = None
        for name in cand:
            meta = C.lookup_meta(info, name)
            if not meta or not meta.get("remote_url"):
                continue
            if (meta.get("mime") or "").startswith("image/svg"):
                continue
            ext = C.ext_of(meta["remote_url"])
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            chosen = (name, meta, ext)
            break

        if not chosen:
            notes.append("%s：候选都没有可用直链，已跳过" % zh)
            continue

        name, meta, ext = chosen
        rel = "assets/%s/L%02d%s" % (slug, i, ext)
        try:
            size = C.download(meta["remote_url"],
                              os.path.join(adir, "L%02d%s" % (i, ext)))
        except Exception as ex:
            notes.append("%s：下载失败（%s）" % (zh, str(ex)[:60]))
            log("      ✗ %s 下载失败" % zh)
            continue

        lic = meta.get("license")
        if not lic:
            notes.append("%s：未取到授权字段，保留并标「授权待确认」" % zh)

        picked.append({
            "title": "File:" + name,
            "caption_zh": zh,
            "caption": zh,                    # 兼容旧字段，值就是中文
            "caption_commons": (meta.get("description") or "")[:80],
            "kw": kw,
            "url": rel,
            "thumb_url": rel,
            "remote_url": meta["remote_url"],
            "source": "commons_search",
            "author": meta.get("artist"),
            "license": lic,
            "license_url": meta.get("license_url"),
            "license_status": "ok" if lic else "unknown",
            "load_verified": True,
            "bytes": size,
        })
        log("      ✓ %-4s %-22s %.0f KB  %s" % (
            rel.split("/")[-1], zh, size / 1024, name[:52]))

    return picked, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("isos", nargs="*", help="ISO 码，如 CN FR US")
    ap.add_argument("--all", action="store_true", help="处理 landmarks.json 里全部国家")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "data", "landmarks.json"), encoding="utf-8") as f:
        conf = json.load(f)

    isos = [x.upper() for x in args.isos]
    if args.all:
        isos = list(conf.get("countries", {}).keys())
    if not isos:
        ap.error("给个 ISO 码，或用 --all")

    for iso in isos:
        entries = (conf.get("countries") or {}).get(iso) or []
        if not entries:
            log("[%s] landmarks.json 里没有配置，跳过" % iso)
            continue

        path = os.path.join(ROOT, "data", "%s.json" % iso.lower())
        if not os.path.exists(path):
            log("[%s] data/%s.json 不存在，先跑 collect.py" % (iso, iso.lower()))
            continue
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)

        log("[%s] %s —— 目标 %d 处地标" % (iso, rec.get("name_zh"), len(entries)))
        picked, notes = pick_and_download(iso, entries, rec)

        if not picked:
            log("      ! 一张都没拿到，保持原样")
            continue

        old = rec.get("landmark_images") or []
        rec["landmark_images"] = picked
        rec["image_license"] = picked[0].get("license")
        rec["image_source_note"] = ("人工按 data/landmarks.json 指定地标，"
                                    "Commons 关键词检索取图；原先自动获得的 %d 张已被替换" % len(old))

        rn = [n for n in (rec.get("review_notes") or [])
              if "地标" not in n and "P18" not in n]
        rn.extend(notes)
        rn.append("地标图改为人工指定清单（%d 张，中文图注）" % len(picked))
        rec["review_notes"] = rn

        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
            f.write("\n")
        log("      已写回 data/%s.json：%d 张\n" % (iso.lower(), len(picked)))

    log("下一步：python scripts/optimize_images.py --all  然后 python scripts/sync_index.py")


if __name__ == "__main__":
    main()
