#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载每处地标的多个候选图到 review/candidates/，供人工挑选。

用法：
    python scripts/pick_candidates.py            # 每处地标最多 4 个候选
    python scripts/pick_candidates.py --per 6

为什么不让脚本直接定：
    前两轮都用"脚本自己选一张"的方式，结果 12 张里 6 张不合格 ——
    搜"战神广场"能拿到没有铁塔的鸟瞰、搜"圣米歇尔山"能拿到同名教堂、
    搜"太和殿"能拿到屋檐斗拱特写。**"哪张图好看"这件事没法靠规则判**。

    所以改成两步：
      1. 脚本只负责"把可能合适的都抓下来"（本地留档，不写 data/*.json）
      2. 人看候选图挑一张，由 assemble 脚本落到 assets/

    这样只需要联网一次，之后挑选与组装全在本地完成。
"""

import argparse
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "review", "candidates")

_spec = importlib.util.spec_from_file_location(
    "atlas_fill", os.path.join(ROOT, "scripts", "fill_images.py"))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)
C = F.C


def norm(s):
    return (s or "").lower().replace("_", "").replace(" ", "").replace("-", "")


def token_ok(filename, en):
    """P18 的文件名千奇百怪（Potala.jpg / WhiteHouseSouthFacade.JPG），
    但至少应包含该地标的英文关键词。这条拦住了把摩泽尔省某教堂当成圣米歇尔山的情况。"""
    if not en:
        return True
    n = norm(filename)
    for t in en.split("|"):
        if norm(t) in n:
            return True
    return False


def gather(entry, per):
    """按可信度收集候选：Wikidata P18 → 中文维基首图 → Commons 关键词搜索"""
    zh = entry["zh"]
    en = entry.get("en", "")
    must = entry.get("must", "")
    avoid = [a.lower() for a in (entry.get("avoid") or [])]
    queries = entry.get("queries") or [zh]
    cands, seen = [], set()

    def add(name, source, meta_check=True):
        if not name or name in seen:
            return
        if C.is_bad_image(name):
            return
        low = name.lower()
        if any(a in low for a in avoid):
            return
        seen.add(name)
        cands.append({"file": name, "source": source})

    # 1) Wikidata P18（多个检索词都试）
    for q in queries:
        hits, _ = F.wikidata_lead_images(q)
        for h in hits:
            if token_ok(h["file"], en):
                add(h["file"], "wikidata_p18:%s" % h.get("label", "")[:16])

    # 2) 中文维基首图
    for q in queries:
        wname, _ = F.wikipedia_lead_image(q)
        if wname and token_ok(wname, en):
            add(wname, "wikipedia_lead")

    # 3) Commons 关键词搜索（这一级才用 must）
    for q in queries:
        kw = entry.get("kw") or q
        for name in F.search_files(kw, limit=20):
            if must and must.lower() not in norm(name):
                continue
            add(name, "commons_search")

    if not cands:
        return []

    # 只对 top N 取元数据，省请求
    picked = cands[: max(per * 3, 10)]
    info = C.commons_imageinfo([c["file"] for c in picked], width=1400)

    scored = []
    for c in picked:
        meta = C.lookup_meta(info, c["file"])
        if not meta or not meta.get("remote_url"):
            continue
        if (meta.get("mime") or "").startswith("image/svg"):
            continue
        sc, why = F.score(c["file"], meta,
                          None if not c["source"].startswith("commons_search") else None)
        if sc is None:
            continue
        # 精选来源加分，保证顺序稳定
        if c["source"].startswith("wikidata_p18"):
            sc += 4
        elif c["source"] == "wikipedia_lead":
            sc += 3
        scored.append((sc, c, meta))

    scored.sort(key=lambda x: -x[0])
    return scored[:per]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=4)
    ap.add_argument("isos", nargs="*")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "data", "landmarks.json"), encoding="utf-8") as f:
        conf = json.load(f)
    isos = [x.upper() for x in args.isos] or list(conf["countries"].keys())

    os.makedirs(OUTDIR, exist_ok=True)
    manifest = {}

    for iso in isos:
        entries = conf["countries"].get(iso) or []
        manifest[iso] = []
        for n, entry in enumerate(entries, 1):
            zh = entry["zh"]
            print("[%s-%02d] %s" % (iso, n, zh), flush=True)
            best = gather(entry, args.per)
            if not best:
                print("        [x] 没有可用候选")
                manifest[iso].append({"n": n, "zh": zh, "candidates": []})
                continue
            item = {"n": n, "zh": zh, "candidates": []}
            for k, (sc, c, meta) in enumerate(best, 1):
                ext = C.ext_of(meta["remote_url"])
                fn = "%s_%02d_%d%s" % (iso, n, k, ext)
                dest = os.path.join(OUTDIR, fn)
                try:
                    size = C.download(meta["remote_url"], dest)
                except Exception as e:
                    print("        [x] 下载失败 %s（%s）" % (c["file"][:40], str(e)[:40]))
                    continue
                print("        %d. %.2f分 %6.0fKB %s  [%s]" % (
                    k, sc, size / 1024, c["file"][:46], c["source"][:20]))
                item["candidates"].append({
                    "k": k, "file": fn, "origin": c["file"],
                    "source": c["source"], "score": round(sc, 2),
                    "width": meta.get("width"), "height": meta.get("height"),
                    "license": meta.get("license"), "author": meta.get("artist"),
                    "remote_url": meta["remote_url"], "bytes": size,
                })
            manifest[iso].append(item)

    with open(os.path.join(ROOT, "review", "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total = sum(len(i["candidates"]) for v in manifest.values() for i in v)
    print("\n合计 %d 个候选，已写入 review/candidates/ 与 review/candidates.json" % total)
    print("下一步：python scripts/contact_sheet.py --candidates   然后把选中的填进 review/choices.json")


if __name__ == "__main__":
    main()
