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
MIN_WIDTH = 900          # 低于这个宽度在详情面板里会糊
MAX_ASPECT = 2.2         # 超过这个宽高比是全景长条（5:1 的故宫全景），主体被压成一条
TARGET_ASPECT = 1.45     # 面板是 4:3，越接近越好
MAX_PER_COUNTRY = 5


def log(msg=""):
    print(msg, flush=True)


def search_files(kw, limit=20):
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


def score(cand, meta, must):
    """给候选打分。三条硬性要求全在 must/宽/长宽比上，不满足直接淘汰。
    踩过的坑：搜 "Eiffel Tower from Champ de Mars" 拿到一张鸟瞰战神广场、
    铁塔在画面外的照片；搜"故宫太和殿"拿到 5:1 的全景长条。光靠关键词不够。"""
    name = (cand or "").replace("_", " ").lower()
    if must and must.lower() not in name:
        return None, "文件名不含「%s」" % must
    w = meta.get("width") or 0
    if w < MIN_WIDTH:
        return None, "宽度仅 %d px" % w
    try:
        ar = float(meta.get("aspect") or 0)
    except Exception:
        ar = 0
    if not ar:
        hh = meta.get("height") or 0
        if w and hh:
            ar = float(w) / hh
    if ar > MAX_ASPECT:
        return None, "宽高比 %.1f 过宽（全景）" % ar
    s = 0.0
    if 1.15 <= ar <= 1.85:
        s += 3
    s += max(0.0, 2 - abs(ar - TARGET_ASPECT) * 2)
    if w >= 1400:
        s += 2
    elif w >= 1100:
        s += 1
    return s, "score=%.1f ar=%.2f w=%d" % (s, ar, w)


def wikidata_lead_images(zh_name, limit=4):
    """用中文名在 Wikidata 搜条目，取 P18（代表图）文件名。

    为什么换这条路：Commons 关键词搜索靠运气 —— 搜 Mont Saint-Michel 会返回
    "Cistern of the Chaplaincy of the Mont Saint-Michel Abbey"（修道院蓄水池），
    搜 Eiffel Tower 会返回 "Sous la Tour Eiffel"（塔底仰拍）。地标名只是文件名里
    的上下文，不代表它是主体。

    P18 是维基百科词条首图用的那一张，由编辑挑过，是"最能代表该条目"的照片，
    比关键词命中要可靠得多。
    """
    out = []
    try:
        q = C.api_json("https://www.wikidata.org/w/api.php", {
            "action": "wbsearchentities", "search": zh_name, "language": "zh",
            "uselang": "zh", "type": "item", "limit": str(limit), "format": "json",
        })
    except Exception as e:
        return out, "Wikidata 搜索失败：%s" % str(e)[:60]

    for hit in (q.get("search") or []):
        qid = hit.get("id")
        if not qid:
            continue
        try:
            ent = json.loads(C.http_get(C.ENTITY_DATA % qid,
                                        accept="application/json").decode("utf-8"))
        except Exception:
            continue
        e = (ent.get("entities") or {}).get(qid)
        if not e:
            continue
        label = ((e.get("labels") or {}).get("zh", {}) or {}).get("value") or hit.get("label")
        for v in C.claim_values(e, "P18"):
            if isinstance(v, str) and not C.is_bad_image(v):
                out.append({"file": v, "qid": qid, "label": label})
        if out:
            break
    return out, None


def wikipedia_lead_image(zh_name):
    """中文维基词条首图。比 P18 更贴近中文命名（"凡尔赛宫镜厅"能直接命中镜厅词条）。"""
    try:
        d = C.api_json("https://zh.wikipedia.org/w/api.php", {
            "action": "query", "prop": "pageimages", "piprop": "name|original",
            "redirects": "1", "titles": zh_name, "format": "json", "formatversion": "2",
        })
    except Exception:
        return None, None
    pages = (d.get("query") or {}).get("pages") or []
    if not pages:
        return None, None
    pg = pages[0]
    if pg.get("missing"):
        return None, None
    name = pg.get("pageimage")
    title = pg.get("title")
    if not name or C.is_bad_image(name):
        return None, None
    return name, title


def pick_and_download(iso, entries, rec):
    slug = iso.lower()
    adir = os.path.join(ROOT, "assets", slug)
    os.makedirs(adir, exist_ok=True)
    picked, notes = [], []

    for i, e in enumerate(entries[:MAX_PER_COUNTRY], 1):
        kw, zh = e.get("kw"), e.get("zh")
        must = e.get("must")

        # 先问 Wikidata 要代表图，拿不到再用关键词搜
        lead, err = wikidata_lead_images(zh)
        source_kind = "wikidata_p18"
        cand = [x["file"] for x in lead]
        if lead:
            log("      · %s Wikidata P18 → %s（%s）" % (zh, lead[0]["file"][:44], lead[0]["label"]))
        else:
            wname, wtitle = wikipedia_lead_image(zh)
            if wname:
                cand = [wname]
                source_kind = "wikipedia_lead"
                log("      · %s 中文维基首图 → %s（%s）" % (zh, wname[:44], wtitle))
            else:
                cand = search_files(kw)
                source_kind = "commons_search"
                log("      · %s 前两级都无图（%s），退到关键词搜索" % (zh, err or "无 P18"))

        if not cand:
            notes.append("%s：Wikidata 与 Commons 都没找到可用图，已跳过" % zh)
            log("      ✗ %s 搜不到" % zh)
            continue

        info = C.commons_imageinfo(cand, width=1400)
        scored, rejects = [], []
        for name in cand:
            meta = C.lookup_meta(info, name)
            if not meta or not meta.get("remote_url"):
                continue
            if (meta.get("mime") or "").startswith("image/svg"):
                continue
            ext = C.ext_of(meta["remote_url"])
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            # P18 是编辑挑过的首图，不再用 must 卡它；must 只约束关键词搜索的结果
            curated = source_kind in ("wikidata_p18", "wikipedia_lead")
            sc, why = score(name, meta, None if curated else must)
            if sc is None:
                rejects.append("%s（%s）" % (name[:40], why))
                continue
            scored.append((sc, name, meta, ext))

        if not scored:
            notes.append("%s：%d 个候选全部未通过筛选：%s"
                         % (zh, len(rejects), "；".join(rejects[:3]) if rejects else "无"))
            log("      ✗ %s 候选全被筛掉" % zh)
            continue

        scored.sort(key=lambda x: -x[0])
        _, name, meta, ext = scored[0]
        log("      · %s ← %d 个候选，选中 1 个（%s）" % (zh, len(scored), name[:44]))
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
            "source": source_kind,
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
