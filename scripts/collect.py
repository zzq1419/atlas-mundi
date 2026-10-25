#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""寰宇图志 · 构建期采集脚本（单国）

用法：
    python scripts/collect.py CN --check      # 只做连通性体检，不采集
    python scripts/collect.py CN              # 采集一国，图片下载进 assets/
    python scripts/collect.py CN --qid Q148   # 手动指定 Wikidata QID
    python scripts/collect.py CN --geo        # 额外抓 Natural Earth 50m 边界

设计原则：
1. 只用标准库，不需要 pip install
2. 只在构建期跑一次，产物全部落盘；运行时前端只读本地文件
3. 任何一步失败都不中断整体，缺口写进 review_notes —— 不隐藏问题
4. 素材下载到 assets/{iso}/，JSON 存相对路径，保证断网也能演示

数据源与字段归属（交接文档第 5、6 节）：
    Wikidata      -> ISO 码 / 坐标 / 首都 / 语言 / 大洲 / P18 图 / P443 发音
                     走 Special:EntityData，不用 SPARQL —— SPARQL 在部分代理下会
                     返回 200 但 bindings 为空，极难排查（v0.1 就栽在这）
    Wikipedia API -> 摘要（extracts + variant=zh-cn，比 REST summary 长且是简体）
    Commons API   -> 图片真实地址 + extmetadata 授权
    Natural Earth -> 国界多边形（--geo 才跑）

授权策略（三级，不因缺授权就一张图都没有）：
    A 有 extmetadata 授权     -> license 写入，license_status=ok
    B 无授权但有文件直链       -> 保留图片，license_status=unknown，页面标「授权待确认」
    C 连文件直链都拿不到       -> 丢弃，记入 review_notes
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    enc = (sys.stdout.encoding or "").lower()
    if enc not in ("utf-8", "utf8", "cp936", "gbk", "gb2312", "cp65001"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UA = "AtlasMundi/0.1 (course project; contact: 2036829270@qq.com)"
TZ = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENTITY_DATA = "https://www.wikidata.org/wiki/Special:EntityData/%s.json"
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ZH_WIKI_API = "https://zh.wikipedia.org/w/api.php"
NE_50M = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "master/geojson/ne_50m_admin_0_countries.geojson")

# ISO -> QID。首批三国写死；扩量时补这张表，或用 --qid 指定。
ISO_QID = {"CN": "Q148", "FR": "Q142", "US": "Q30"}

# Wikidata 的 zh 标签常给全称，卡片要短名。补在这里，按需扩展。
SHORT_NAME = {"Q148": ["中国"], "Q142": ["法国"], "Q30": ["美国"]}

# P37 返回的是语言条目的 QID（如 Q150=法语），转成 BCP47 才好用。
# 只覆盖首批三国及常见语种，扩量时补这张表；查不到就保留 QID。
LANG_CODE = {
    "Q150": "fr", "Q1860": "en", "Q727694": "zh", "Q7850": "zh",
    "Q9186": "yue", "Q835866": "zh", "Q24841726": "zh",
    "Q12107": "br", "Q14185": "oc", "Q652": "it", "Q1321": "es",
    "Q188": "de", "Q7737": "ru", "Q5287": "ja", "Q9176": "ko",
    "Q8748": "ar", "Q5146": "pt",
}

# P37 常见上下位概念，展示时丢弃（保留「现代标准汉语」这类最具体的）
LANG_DROP = {"中文", "汉语", "中国语言", "Chinese", "Chinese language",
             "普通话", "Standard Chinese"}


def is_zh_audio(name):
    """P443 只保证「有发音文件」，不保证语种。实测 Q148 首个是 Lb-China.ogg
    （卢森堡语读的 China）。只采信文件名里明确带中文标记的。"""
    low = (name or "").lower()
    return any(k in low for k in ("zh-", "zh_", "chinese", "中文", "cmn-", "yue-"))


# ---------------------------------------------------------------- 基础工具
def log(msg=""):
    print(msg, flush=True)


def http_get(url, timeout=45, retries=3, accept=None):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", UA)
            if accept:
                req.add_header("Accept", accept)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read()[:200].decode("utf-8", "replace")
            except Exception:
                pass
            last = "HTTP %s %s" % (e.code, body.replace("\n", " "))
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        if i < retries - 1:
            time.sleep(2 + i * 2)
    raise RuntimeError("请求失败 %s（%s）" % (url.split("?")[0], last))


def api_json(base, params, timeout=45):
    url = base + "?" + urllib.parse.urlencode(params)
    raw = http_get(url, timeout=timeout, accept="application/json")
    txt = raw.decode("utf-8", "replace")
    try:
        return json.loads(txt)
    except Exception:
        raise RuntimeError("返回不是 JSON，前 120 字：%s" % txt[:120].replace("\n", " "))


def strip_html(s):
    if not s:
        return None
    s = re.sub(r"<[^>]+>", "", s)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&#039;", "'"), ("&nbsp;", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def ext_of(url, default=".jpg"):
    p = urllib.parse.urlparse(url).path
    ext = os.path.splitext(p)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".ogg", ".oga", ".mp3", ".wav", ".flac", ".opus"):
        return ".jpg" if ext == ".jpeg" else ext
    return default


def norm_title(t):
    """Commons 标题会把下划线换成空格，统一成可比形式"""
    return (t or "").replace("File:", "").replace("_", " ").strip().lower()


def lookup_meta(info, name):
    return (info or {}).get(norm_title(name))


def download(url, dest, timeout=120):
    data = http_get(url, timeout=timeout, retries=2)
    if len(data) < 1024:
        raise RuntimeError("文件过小（%d 字节），疑似错误页" % len(data))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


# ---------------------------------------------------------------- 连通性体检
def preflight():
    """先看四个域名通不通，不通就直接说清楚，别让用户对着结果瞎猜"""
    log("== 连通性体检 ==")
    targets = [
        ("https://www.wikidata.org/w/api.php?action=query&meta=siteinfo&format=json", "Wikidata"),
        ("https://zh.wikipedia.org/w/api.php?action=query&meta=siteinfo&format=json", "中文维基"),
        ("https://commons.wikimedia.org/w/api.php?action=query&meta=siteinfo&format=json", "Commons"),
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/"
         "The_Great_Wall_of_China_at_Jinshanling-edit.jpg/200px-"
         "The_Great_Wall_of_China_at_Jinshanling-edit.jpg", "upload 图床"),
    ]
    ok = 0
    for url, label in targets:
        t0 = time.time()
        try:
            n = len(http_get(url, timeout=12, retries=1))
            log("  ✓ %-11s %5.1fs  %d 字节" % (label, time.time() - t0, n))
            ok += 1
        except Exception as e:
            log("  ✗ %-11s %s" % (label, str(e)[:90]))
    log("  体检：%d / %d 可达" % (ok, len(targets)))
    if ok == 0:
        log("  → 全部不可达，八成是代理没开或规则没覆盖维基媒体。\n")
    else:
        log()
    return ok


# ---------------------------------------------------------------- 1. Wikidata
def fetch_labels(qids):
    qids = [q for q in dict.fromkeys(qids) if q]
    out = {}
    for i in range(0, len(qids), 40):
        try:
            d = api_json(WD_API, {"action": "wbgetentities", "ids": "|".join(qids[i:i + 40]),
                                  "props": "labels", "languages": "zh|zh-cn|en",
                                  "format": "json"})
        except Exception as e:
            log("      ! 取标签失败：%s" % str(e)[:80])
            continue
        for qid, ent in (d.get("entities") or {}).items():
            lb = ent.get("labels") or {}
            for lang in ("zh-cn", "zh", "en"):
                if lb.get(lang, {}).get("value"):
                    out[qid] = lb[lang]["value"]
                    break
    return out


def claim_values(entity, prop):
    """解包某属性的 mainsnak datavalue 列表"""
    out = []
    for st in (entity.get("claims") or {}).get(prop, []):
        sn = st.get("mainsnak") or {}
        if sn.get("snaktype") != "value":
            continue
        dv = (sn.get("datavalue") or {}).get("value")
        if dv is not None:
            out.append(dv)
    return out


def entity_id(v):
    return v.get("id") if isinstance(v, dict) and v.get("id") else None


def fetch_wikidata(iso2, forced_qid, notes):
    log("[1/4] Wikidata 实体 …")
    qid = forced_qid or ISO_QID.get(iso2)
    if not qid:
        notes.append("没有 %s 的 QID 映射，请用 --qid 指定，或补进 ISO_QID 表" % iso2)
        log("      ✗ 未配置 QID，跳过")
        return {}

    try:
        d = json.loads(http_get(ENTITY_DATA % qid, accept="application/json").decode("utf-8"))
    except Exception as e:
        notes.append("Wikidata 实体拉取失败（%s）：%s" % (qid, str(e)[:100]))
        log("      ✗ %s 拉取失败：%s" % (qid, str(e)[:110]))
        return {}

    ent = (d.get("entities") or {}).get(qid)
    if not ent:
        notes.append("Wikidata 实体 %s 返回为空" % qid)
        log("      ✗ 实体为空")
        return {}

    out = {"qid": qid}
    labels = ent.get("labels") or {}
    if labels.get("zh", {}).get("value"):
        out["name_zh"] = labels["zh"]["value"]
    elif labels.get("zh-cn", {}).get("value"):
        out["name_zh"] = labels["zh-cn"]["value"]
    if labels.get("en", {}).get("value"):
        out["name_en"] = labels["en"]["value"]

    iso2_vals = claim_values(ent, "P297")
    if iso2_vals:
        out["iso_a2"] = str(iso2_vals[0])
    else:
        out["iso_a2"] = iso2
    iso3_vals = claim_values(ent, "P298")
    if iso3_vals:
        out["iso_a3"] = str(iso3_vals[0])
    else:
        notes.append("Wikidata 无 P298（三字母码）")

    coords = claim_values(ent, "P625")
    if coords and isinstance(coords[0], dict) and "latitude" in coords[0]:
        out["centroid"] = [round(coords[0]["longitude"], 4), round(coords[0]["latitude"], 4)]
    else:
        notes.append("Wikidata 无 P625（坐标）")

    cap_vals = claim_values(ent, "P36")
    cap_id = entity_id(cap_vals[0]) if cap_vals else None
    con_ids = [entity_id(v) for v in claim_values(ent, "P30") if entity_id(v)]
    lang_ids = [entity_id(v) for v in claim_values(ent, "P37") if entity_id(v)]
    lab = fetch_labels([q for q in ([cap_id] + con_ids + lang_ids) if q])

    if cap_id:
        out["capital"] = lab.get(cap_id)
    else:
        notes.append("Wikidata 无 P36（首都）")
    if con_ids:
        out["continent"] = lab.get(con_ids[0])
    if lang_ids:
        raw = [{"code": LANG_CODE.get(q, q), "name_zh": lab.get(q) or q,
                "name_local": lab.get(q) or q,
                "role": "official", "audio_url": None, "audio_source": None,
                "audio_status": "pending"} for q in lang_ids]
        # P37 会同时给出「中文 / 汉语 / 现代标准汉语 / 普通话」这类上下位概念，
        # 直接展示等于在面板里堆同义词。这里只保留最具体的那个。
        seen, keep = set(), []
        for l in raw:
            if l["name_zh"] in LANG_DROP:
                continue
            if l["name_zh"] in seen:
                continue
            seen.add(l["name_zh"])
            keep.append(l)
        out["languages"] = keep[:2] or raw[:1]
        if len(raw) > len(out["languages"]):
            notes.append("P37 返回 %d 个语言，去重/去上位概念后保留 %d 个：%s"
                         % (len(raw), len(out["languages"]),
                            "、".join(l["name_zh"] for l in out["languages"])))

    # 名称：短的是常用名，长的是全称。卡片显示常用名（中国 而非 中华人民共和国）
    nzh, nen = out.get("name_zh"), out.get("name_en")
    if nzh and len(nzh) > 6:
        out["name_official"] = nzh
        for short in SHORT_NAME.get(qid, []):
            if short != nzh:
                out["name_zh"] = short
                break

    out["_image_files"] = [v for v in claim_values(ent, "P18") if isinstance(v, str)][:5]
    out["_audio_files"] = [v for v in claim_values(ent, "P443") if isinstance(v, str)][:3]
    sl = ent.get("sitelinks") or {}
    if sl.get("zhwiki", {}).get("title"):
        out["_wiki_title"] = sl["zhwiki"]["title"]

    if not out["_image_files"]:
        notes.append("Wikidata 无 P18 代表图，回退到维基正文配图")
    log("      ✓ %s  %s  首都=%s  坐标=%s  语言=%d  P18=%d  P443=%d"
        % (qid, out.get("name_zh"), out.get("capital"), out.get("centroid"),
           len(out.get("languages") or []), len(out["_image_files"]), len(out["_audio_files"])))
    return out


# ---------------------------------------------------------------- 2. Wikipedia
def wiki_extract(title, notes):
    """正文摘要：extracts 比 REST summary 长得多，variant=zh-cn 保证简体"""
    if not title:
        return None, None
    for chars in (900, 700, 500):
        try:
            d = api_json(ZH_WIKI_API, {
                "action": "query", "prop": "extracts", "explaintext": 1,
                "exchars": chars, "variant": "zh-cn", "redirects": 1,
                "titles": title, "format": "json", "formatversion": 2,
            })
        except Exception as e:
            notes.append("extracts 取摘要失败（%d 字档）：%s" % (chars, str(e)[:80]))
            continue
        pages = (d.get("query") or {}).get("pages") or []
        if not pages:
            continue
        text = (pages[0].get("extract") or "").strip()
        if len(text) >= 120:
            return text, pages[0].get("title")
    return None, None


def trim_summary(text, low=300, high=500):
    """压到 300~500 字，优先在句末切"""
    if not text or len(text) <= high:
        return text
    cut = text[:high]
    pos = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
    if pos >= low:
        return cut[:pos + 1]
    return cut.rstrip("，、；,;") + "……"


def fetch_summary(title, notes):
    log("[2/4] Wikipedia 摘要 …")
    text, real_title = wiki_extract(title, notes)
    if not text:
        notes.append("Wikipedia 未取到正文摘要")
        log("      ✗ 未取到")
        return None
    text = trim_summary(text)
    log("      ✓ %d 字（标题：%s）" % (len(text), real_title))
    if len(text) < 300:
        notes.append("摘要仅 %d 字，低于 300 字下限，需人工或 LLM 补写" % len(text))
    return {"text": text, "title": real_title,
            "url": "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(real_title or ""),
            "chars": len(text)}


# ---------------------------------------------------------------- 3. Commons
def commons_imageinfo(files, width=900):
    out = {}
    titles = ["File:" + f for f in files]
    for i in range(0, len(titles), 10):
        params = {"action": "query", "format": "json", "prop": "imageinfo",
                  "iiprop": "url|extmetadata|size|mime", "titles": "|".join(titles[i:i + 10])}
        if width:
            params["iiurlwidth"] = str(width)
        try:
            d = api_json(COMMONS_API, params)
        except Exception:
            continue
        for page in (d.get("query", {}).get("pages", {}) or {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            if not ii.get("url"):
                continue
            meta = ii.get("extmetadata") or {}
            out[norm_title(page.get("title", ""))] = {
                "remote_url": ii.get("thumburl") or ii.get("url"),
                "original_url": ii.get("url"),
                "mime": ii.get("mime"),
                "license": strip_html(meta.get("LicenseShortName", {}).get("value")),
                "license_url": meta.get("LicenseUrl", {}).get("value"),
                "artist": strip_html(meta.get("Artist", {}).get("value")),
                "description": strip_html(meta.get("ImageDescription", {}).get("value")),
            }
    return out


def article_images(title, limit=4):
    """P18 为空时的回退：取维基正文用到的图片文件名，过滤掉图标/地图/旗帜"""
    if not title:
        return []
    try:
        d = api_json(ZH_WIKI_API, {"action": "query", "prop": "images", "imlimit": "40",
                                   "redirects": 1, "titles": title, "format": "json",
                                   "formatversion": 2})
    except Exception:
        return []
    pages = (d.get("query") or {}).get("pages") or []
    if not pages:
        return []
    bad = ("icon", "logo", "question_book", "disambig", "edit-clear", "padlock",
           "flag_of", "emblem", "coat_of_arms", "_map", "map_of", "location", "commons-")
    out = []
    for im in pages[0].get("images") or []:
        name = (im.get("title") or "").replace("File:", "")
        low = name.lower()
        if not low.endswith((".jpg", ".jpeg", ".png")):
            continue
        if any(b in low for b in bad):
            continue
        out.append(name)
        if len(out) >= limit:
            break
    return out


def fetch_assets(iso2, wd, notes):
    log("[3/4] Commons 图片与发音 …")
    slug = iso2.lower()
    adir = os.path.join(ROOT, "assets", slug)
    images, audio = [], None

    files = list(wd.get("_image_files") or [])
    src_kind = "P18"
    if not files:
        files = article_images(wd.get("_wiki_title"))
        src_kind = "维基正文配图"
        log("      P18 为空，改用正文配图（%d 个候选）" % len(files))

    info = commons_imageinfo(files) if files else {}
    for idx, name in enumerate(files[:3], 1):
        meta = lookup_meta(info, name)
        if not meta or not meta.get("remote_url"):
            notes.append("图片 %s 未取到直链，已跳过" % name)
            log("      ✗ %s 无直链" % name)
            continue
        ext = ext_of(meta["remote_url"])
        rel = "assets/%s/%02d%s" % (slug, idx, ext)
        try:
            size = download(meta["remote_url"], os.path.join(adir, "%02d%s" % (idx, ext)))
        except Exception as e:
            notes.append("图片 %s 下载失败：%s" % (name, str(e)[:80]))
            log("      ✗ %s 下载失败：%s" % (name, str(e)[:60]))
            continue
        lic = meta.get("license")
        if not lic:
            notes.append("图片 %s 未取到授权，保留并标为「授权待确认」" % name)
        images.append({
            "title": "File:" + name,
            "caption": (meta.get("description") or "").split("。")[0][:60] or name,
            "url": rel, "thumb_url": rel, "remote_url": meta["remote_url"],
            "source": "commons", "origin_kind": src_kind,
            "author": meta.get("artist"), "license": lic,
            "license_url": meta.get("license_url"),
            "license_status": "ok" if lic else "unknown",
            "load_verified": True, "bytes": size,
        })
        log("      ✓ %s  %.0f KB  授权=%s" % (rel, size / 1024, lic or "待确认"))

    cand = [n for n in (wd.get("_audio_files") or []) if is_zh_audio(n)]
    dropped = [n for n in (wd.get("_audio_files") or []) if not is_zh_audio(n)]
    if dropped:
        notes.append("P443 发音语种不符已弃用：%s（P443 不保证语种，须按文件名筛）"
                     % "、".join(dropped))
    if not cand and (wd.get("_audio_files") or []):
        notes.append("无中文发音可用，改跑 python scripts/tts_local.py %s \"中文名\"" % iso2)

    for name in cand[:1]:
        meta = lookup_meta(commons_imageinfo([name], width=0), name)
        if not meta or not meta.get("original_url"):
            notes.append("发音文件 %s 未取到直链" % name)
            continue
        ext = ext_of(meta["original_url"], ".ogg")
        rel = "assets/%s/pronunciation%s" % (slug, ext)
        try:
            size = download(meta["original_url"], os.path.join(adir, "pronunciation" + ext))
        except Exception as e:
            notes.append("发音下载失败：%s" % str(e)[:80])
            continue
        audio = {"url": rel, "source": "commons", "origin_title": "File:" + name,
                 "license": meta.get("license"), "license_url": meta.get("license_url"),
                 "author": meta.get("artist"), "bytes": size}
        log("      ✓ %s  %.0f KB" % (rel, size / 1024))

    if not images:
        notes.append("本次未获得任何可用地标图（连文件直链都没拿到）")
    if not audio:
        notes.append("Commons 无可用发音，语音走构建期 TTS 兜底（待接）")
    return images, audio


# ---------------------------------------------------------------- 4. 边界
def fetch_geo(iso2, notes):
    log("[4/4] Natural Earth 50m 边界 …（首次约 24MB）")
    cache = os.path.join(ROOT, "geo", "_ne_50m_countries.geojson")
    if not os.path.exists(cache):
        try:
            size = download(NE_50M, cache, timeout=300)
            log("      已下载（%.0f MB）" % (size / 1048576))
        except Exception as e:
            notes.append("Natural Earth 下载失败：%s" % str(e)[:80])
            return None, None
    with open(cache, encoding="utf-8") as f:
        fc = json.load(f)
    for feat in fc.get("features", []):
        p = feat.get("properties", {})
        codes = {(p.get("ISO_A2") or "").upper(), (p.get("ISO_A2_EH") or "").upper(),
                 (p.get("WB_A2") or "").upper()}
        if iso2.upper() in codes:
            name = p.get("NAME_ZH") or p.get("NAME")
            out = os.path.join(ROOT, "geo", "%s.geojson" % iso2.lower())
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                json.dump({"type": "FeatureCollection", "features": [feat]},
                          f, ensure_ascii=False)
            log("      ✓ geo/%s.geojson <- %s（%s）" % (iso2.lower(), name, p.get("CONTINENT")))
            return "geo/%s.geojson" % iso2.lower(), name
    notes.append("Natural Earth 中未找到 ISO_A2=%s 的要素（微国家常见）" % iso2)
    return None, None


# ---------------------------------------------------------------- 合并
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("iso", help="ISO 3166-1 alpha-2，例如 CN")
    ap.add_argument("--qid", help="手动指定 Wikidata QID")
    ap.add_argument("--geo", action="store_true", help="额外抓 Natural Earth 50m 边界")
    ap.add_argument("--check", action="store_true", help="只做连通性体检")
    args = ap.parse_args()

    iso2 = args.iso.upper()
    ok = preflight()
    if args.check:
        return
    if ok == 0:
        log("!! 四个域名全部不可达，已中止。data/%s.json 未被改动。" % iso2.lower())
        log("   请确认代理已开启且规则覆盖 wikimedia.org / wikipedia.org / wikidata.org")
        return

    data_path = os.path.join(ROOT, "data", "%s.json" % iso2.lower())
    old = {}
    if os.path.exists(data_path):
        with open(data_path, encoding="utf-8") as f:
            old = json.load(f)
        log("读到已有 data/%s.json，保留其中的人工字段\n" % iso2.lower())

    notes = []
    rec = dict(old)

    wd = fetch_wikidata(iso2, args.qid, notes)
    for k in ("qid", "iso_a2", "iso_a3", "name_zh", "name_en", "capital", "continent"):
        if wd.get(k):
            rec[k] = wd[k]
    if wd.get("centroid"):
        rec["centroid"] = wd["centroid"]
        rec["centroid_source"] = "wikidata P625"
    elif old.get("centroid"):
        notes.append("Wikidata 无 P625，沿用人工估算坐标")
    if wd.get("languages"):
        regional = [l for l in (old.get("languages") or []) if l.get("role") == "regional"]
        rec["languages"] = wd["languages"] + regional

    summ = fetch_summary(wd.get("_wiki_title") or rec.get("name_zh"), notes)
    if summ:
        rec["summary_text"] = summ["text"]
        rec["summary_source"] = {"source": "wikipedia_extracts", "url": summ["url"],
                                 "title": summ["title"], "chars": summ["chars"]}

    images, audio = fetch_assets(iso2, wd, notes)
    if images:
        rec["landmark_images"] = images
        ok_lic = [i["license"] for i in images if i.get("license")]
        rec["image_license"] = ok_lic[0] if ok_lic else None
    if audio:
        rec["audio_url"] = audio["url"]
        rec["audio_source"] = "commons"
        rec["audio_meta"] = audio
        for l in rec.get("languages") or []:
            if l.get("role") == "official" and not l.get("audio_url"):
                l["audio_url"] = audio["url"]
                l["audio_source"] = "commons"
                l["audio_status"] = "ok"
                break

    if args.geo:
        geo_rel, geo_name = fetch_geo(iso2, notes)
        if geo_rel:
            rec["geometry"] = geo_rel
            rec["geometry_status"] = "naturalearth_50m"
            rec["geometry_name"] = geo_name

    for k in ("_image_files", "_audio_files", "_wiki_title"):
        rec.pop(k, None)

    rec["schema_version"] = "0.1"
    rec["collected_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    rec["collector"] = "scripts/collect.py v0.2"
    rec["needs_review"] = bool(notes)
    rec["review_notes"] = notes or ["各字段均已取到，待人工复核内容质量"]

    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")

    idx_path = os.path.join(ROOT, "data", "index.json")
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
        for c in idx.get("countries", []):
            if c.get("iso_a2") != iso2:
                continue
            any_img = bool(rec.get("landmark_images"))
            c["name_zh"] = rec.get("name_zh") or c.get("name_zh")
            c["name_en"] = rec.get("name_en") or c.get("name_en")
            c["continent"] = rec.get("continent") or c.get("continent")
            c["capital"] = rec.get("capital") or c.get("capital")
            c["centroid"] = rec.get("centroid") or c.get("centroid")
            c["thumb"] = rec["landmark_images"][0]["thumb_url"] if any_img else None
            c["modalities"] = {"image": any_img, "audio": bool(rec.get("audio_url")),
                               "text": bool(rec.get("summary_text")),
                               "coords": bool(rec.get("centroid")),
                               "geometry": bool(rec.get("geometry"))}
            n = sum(1 for v in c["modalities"].values() if v)
            c["status"] = "complete" if n == 5 else ("partial" if n else "placeholder")
        idx["updated_at"] = datetime.now(TZ).date().isoformat()
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
            f.write("\n")
        log("\n已同步 data/index.json")

    log("\n===== 完成 =====")
    keys = ("qid", "iso_a3", "name_zh", "capital", "continent", "centroid", "languages",
            "landmark_images", "image_license", "summary_text", "custom_text",
            "audio_url", "geometry")
    log("档案 data/%s.json   非空字段 %d / %d" %
        (iso2.lower(), sum(1 for k in keys if rec.get(k)), len(keys)))
    log("图片 %d 张，音频 %s" % (len(rec.get("landmark_images") or []),
                              "有" if rec.get("audio_url") else "无"))
    if notes:
        log("\n待复核（%d 条）：" % len(notes))
        for n in notes:
            log("  · " + n)
    log("\n下一步：把结果告诉助手，由助手核对 JSON 并接前端。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n已中断")
    except Exception as e:
        log("\n!! 采集失败：%s: %s" % (type(e).__name__, e))
        log("   先跑 `python scripts/collect.py CN --check` 看哪一段不通。")
        sys.exit(1)
