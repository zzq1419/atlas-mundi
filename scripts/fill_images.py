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

# 控制台可能是 cp936（Windows cmd 默认），打不出的字符用 ? 代替，别让整段崩掉。
# 之前 collect.py 在连不上某个站时打印一个 ✗ 就 UnicodeEncodeError 退出，
# 看起来像"采集失败"，其实连抓取都还没开始。
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAPS = os.path.join(ROOT, "data", "_image_gaps.json")

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
MAX_CANDIDATES = 26      # 单个地标最多取这么多个候选去做 imageinfo，再多就慢了

# 三档筛选。第一档是"能进画廊"的标准；后两档只在前一档全军覆没时启用。
# 起因：吉萨金字塔群只有一张 "Pyramids of the Giza Necropolis.jpg"，宽高比 2.4，
# 被 2.2 的硬线判成"全景"直接淘汰 —— 结果埃及那一栏没有金字塔。
# 宁可给一张略宽的全景，也比给用户一个空框强。
TIERS = [
    ("strict", {"min_w": MIN_WIDTH, "max_ar": MAX_ASPECT}),
    ("relaxed", {"min_w": 800, "max_ar": 3.2}),
    ("loose", {"min_w": 640, "max_ar": 4.5}),
]
# 编辑挑过的图（P18 / 维基首图）优先于关键词命中：加个权重，分数打平时它赢
SOURCE_BONUS = {"wikidata_p18": 2.5, "wikipedia_lead": 2.0, "commons_search": 0.0}
CURATED = ("wikidata_p18", "wikipedia_lead")

# 关键词命中里混进来的"合影照"：主体是雕塑/展陈/复原模型，地标只是背景。
# 实测搜 "Great Pyramids of Giza" 的第一名是 Forever is Now 艺术展那件巨型金属手，
# 金字塔在远处小得像三颗牙。这类文件名直接毙掉，不给它进候选的机会。
JUNK_WORDS = (
    "exhibition", "installation", "artwork", "sculpture", "replica",
    "model of", "miniature", "painting", "drawing", "engraving",
    "stamp", "banknote", "coin", "logo", "coat of arms", "poster",
    "panorama of", "collage", "montage",
)

# 尝试顺序：先让编辑挑过的图走严格档，不过就放宽一档；关键词命中只接受严格档
# （放宽它会立刻引来上面那种合影照）；最后才拿编辑图的最宽档兜底。
ATTEMPTS = [
    ("curated", "strict"),
    ("curated", "relaxed"),
    ("commons", "strict"),
    ("curated", "loose"),
]


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


def score(cand, meta, must, tier):
    """给候选打分。硬性要求（must/宽/长宽比）按档位放宽，不满足直接淘汰。
    踩过的坑：搜 "Eiffel Tower from Champ de Mars" 拿到一张鸟瞰战神广场、
    铁塔在画面外的照片；搜"故宫太和殿"拿到 5:1 的全景长条。光靠关键词不够。"""
    name = (cand or "").replace("_", " ").lower()
    if must and must.lower() not in name:
        return None, "文件名不含「%s」" % must
    w = meta.get("width") or 0
    if w < tier["min_w"]:
        return None, "宽度仅 %d px" % w
    try:
        ar = float(meta.get("aspect") or 0)
    except Exception:
        ar = 0
    if not ar:
        hh = meta.get("height") or 0
        if w and hh:
            ar = float(w) / hh
    if ar > tier["max_ar"]:
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


def query_variants(entry):
    """一个地标给几条检索词。第一条原样，后面逐步砍掉修饰词。
    Commons 的 File 检索是全文匹配，多写一个词就少一半结果 ——
    "Great Pyramids of Giza" 命中数远少于 "Pyramids Giza"。"""
    out = []
    for key in ("kw", "en"):
        v = (entry.get(key) or "").strip()
        if v and v not in out:
            out.append(v)
    base = (entry.get("kw") or entry.get("en") or "").strip()
    words = [w for w in base.split() if w.lower() not in ("the", "of", "great", "national")]
    if len(words) >= 2:
        v = " ".join(words[-2:])
        if v and v not in out:
            out.append(v)
    return out[:3]


def gather_candidates(entry):
    """按可信度排队收集候选，三路都试（不是命中即停）。
    以前是 if/elif：拿到 P18 就不搜 Commons 了，结果 P18 那张被宽高比筛掉时，
    整处地标就没了 —— 埃及金字塔就是这么丢的。"""
    out, seen = [], set()

    def add(name, kind):
        if name and name not in seen and not C.is_bad_image(name):
            seen.add(name)
            out.append((name, kind))

    lead, err = wikidata_lead_images(entry.get("zh"))
    for x in lead:
        add(x["file"], "wikidata_p18")
    if lead:
        log("      · %s P18 → %s（%s）" % (entry.get("zh"), lead[0]["file"][:42], lead[0]["label"]))
    else:
        wname, wtitle = wikipedia_lead_image(entry.get("zh"))
        if wname:
            add(wname, "wikipedia_lead")
            log("      · %s 维基首图 → %s（%s）" % (entry.get("zh"), wname[:42], wtitle))

    if len(out) < 3:
        for q in query_variants(entry):
            got = search_files(q, limit=12)
            for n in got:
                add(n, "commons_search")
            log("      · %s Commons「%s」→ %d 个候选" % (entry.get("zh"), q, len(got)))
            if len(out) >= MAX_CANDIDATES:
                break
    return out, err


def is_junk(name):
    low = (name or "").replace("_", " ").lower()
    return any(w in low for w in JUNK_WORDS)


def rank_pool(pool, info, must, tier):
    """按档位给一组候选打分，返回 (通过的, 被淘汰的原因)。"""
    scored, rejects = [], []
    for name, kind in pool:
        meta = C.lookup_meta(info, name)
        if not meta or not meta.get("remote_url"):
            continue
        if (meta.get("mime") or "").startswith("image/svg"):
            continue
        ext = C.ext_of(meta["remote_url"])
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        # P18 / 首图是编辑挑过的，不再用 must 卡它；must 只约束关键词搜索的结果
        sc, why = score(name, meta, None if kind in CURATED else must, tier)
        if sc is None:
            rejects.append("%s（%s）" % (name[:38], why))
            continue
        scored.append((sc + SOURCE_BONUS.get(kind, 0), name, meta, ext, kind))
    scored.sort(key=lambda x: -x[0])
    return scored, rejects


def pick_for(entry):
    """在一个地标的候选里挑一张。返回 ((name, meta, ext, tier), None) 或 (None, 原因)。"""
    cands, err = gather_candidates(entry)
    if not cands:
        return None, "Wikidata 与 Commons 都没找到可用图（%s）" % (err or "无结果")

    cands = cands[:MAX_CANDIDATES]
    info = C.commons_imageinfo([n for n, _ in cands], width=1400) or {}
    must = (entry.get("must") or "").strip() or None
    curated = [c for c in cands if c[1] in CURATED]
    searched = [c for c in cands if c[1] not in CURATED and not is_junk(c[0])]
    if len(searched) < len(cands) - len(curated):
        log("      · %s 关键词命中里滤掉 %d 张（雕塑/展陈/复原模型）"
            % (entry.get("zh"), len(cands) - len(curated) - len(searched)))

    pools = {"curated": curated, "commons": searched}
    tiers = dict(TIERS)
    rejects = []
    for pool_name, tier_name in ATTEMPTS:
        pool = pools[pool_name]
        if not pool:
            continue
        scored, rej = rank_pool(pool, info, must, tiers[tier_name])
        if not scored:
            rejects = rej or rejects
            continue
        _, name, meta, ext, kind = scored[0]
        if tier_name != "strict" or pool_name == "commons":
            log("      ! %s 走 %s/%s 档（%d 个候选）"
                % (entry.get("zh"), pool_name, tier_name, len(scored)))
        return (name, meta, ext, tier_name, kind), None

    return None, "%d 个候选全部未通过筛选：%s" % (
        len(cands), "；".join(rejects[:3]) if rejects else "无")


def pick_and_download(iso, entries, rec):
    slug = iso.lower()
    adir = os.path.join(ROOT, "assets", slug)
    os.makedirs(adir, exist_ok=True)
    picked, notes, gaps = [], [], []
    used = set()

    # 已经抓好并落盘的图直接沿用。批量跑到一半重跑、或者只想补某一处地标时，
    # 不要把所有图重新下一遍（重下还会换掉已经人工确认过的那几张）。
    kept = {}
    for it in rec.get("landmark_images") or []:
        k = (it.get("kw") or "").strip().lower()
        if k and it.get("url") and os.path.exists(os.path.join(ROOT, it["url"])):
            kept[k] = it

    for i, e in enumerate(entries, 1):
        if len(picked) >= MAX_PER_COUNTRY:
            break
        kw, zh = e.get("kw"), e.get("zh")

        old = kept.get((kw or "").strip().lower())
        if old:
            picked.append(old)
            used.add(old.get("title"))
            log("      [=] %-22s 沿用已有的 %s" % (zh, str(old.get("url")).split("/")[-1]))
            continue

        got, why = pick_for(e)
        if not got:
            notes.append("%s：%s" % (zh, why))
            gaps.append({"zh": zh, "kw": kw, "reason": why})
            log("      [x] %s %s" % (zh, why))
            continue

        name, meta, ext, tier_name, kind = got
        if name in used:
            notes.append("%s：与前面某处重复（同图），已跳过" % zh)
            gaps.append({"zh": zh, "kw": kw, "reason": "与其他地标同图"})
            continue
        used.add(name)

        rel = "assets/%s/L%02d%s" % (slug, i, ext)
        try:
            size = C.download(meta["remote_url"],
                              os.path.join(adir, "L%02d%s" % (i, ext)))
        except Exception as ex:
            notes.append("%s：下载失败（%s）" % (zh, str(ex)[:60]))
            gaps.append({"zh": zh, "kw": kw, "reason": "下载失败"})
            log("      [x] %s 下载失败" % zh)
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
            "source": kind,
            "pick_tier": tier_name,
            "author": meta.get("artist"),
            "license": lic,
            "license_url": meta.get("license_url"),
            "license_status": "ok" if lic else "unknown",
            "load_verified": True,
            "bytes": size,
        })
        log("      [ok] %-4s %-22s %.0f KB  %s" % (
            rel.split("/")[-1], zh, size / 1024, name[:52]))

    return picked, notes, gaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("isos", nargs="*", help="ISO 码，如 CN FR US")
    ap.add_argument("--all", action="store_true", help="处理 landmarks.json 里全部国家")
    ap.add_argument("--gaps", action="store_true",
                    help="只处理上次留下缺口的国家（读 data/_image_gaps.json）")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "data", "landmarks.json"), encoding="utf-8") as f:
        conf = json.load(f)

    isos = [x.upper() for x in args.isos]
    if args.all:
        isos = list(conf.get("countries", {}).keys())
    if args.gaps:
        old_gaps = read_json(GAPS, {})
        isos = sorted(k for k, v in old_gaps.items() if v)
    if not isos:
        ap.error("给个 ISO 码，或用 --all / --gaps")

    gapmap = read_json(GAPS, {})

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
        picked, notes, gaps = pick_and_download(iso, entries, rec)
        gapmap[iso] = gaps

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
        log("      已写回 data/%s.json：%d 张，缺口 %d 处\n" % (iso.lower(), len(picked), len(gaps)))

    write_json(GAPS, gapmap)
    left = sum(len(v) for v in gapmap.values())
    if left:
        log("缺口合计 %d 处（%d 个国家）→ data/_image_gaps.json" % (left, len(gapmap)))
        log("补缺口：python scripts/fill_images.py --gaps （只重试这些国家，已有的图不动）")
    log("下一步：python scripts/optimize_images.py --all  然后 python scripts/sync_index.py")


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
