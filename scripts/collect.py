#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""寰宇图志 · 构建期采集脚本（单国）

用法：
    python scripts/collect.py CN              # 采集一国，图片下载进 assets/
    python scripts/collect.py CN --geo        # 额外抓 Natural Earth 50m 边界
    python scripts/collect.py CN --only wikidata   # 只跑某一步（调试用）

设计原则：
1. 只用标准库，不需要 pip install
2. 只在构建期跑一次，产物全部落盘；运行时前端只读本地文件
3. 任何一步失败都不中断整体，缺口写进 review_notes —— 不隐藏问题
4. 素材下载到 assets/{iso}/，JSON 里存相对路径，保证断网也能演示

数据源与字段归属（交接文档第 5、6 节）：
    Wikidata SPARQL  -> ISO 码 / 坐标 / 首都 / 语言 / 大洲 / P18 图 / P443 发音
    Wikipedia REST   -> 摘要
    Commons API      -> 图片真实地址 + extmetadata 授权
    Natural Earth    -> 国界多边形（--geo 才跑）
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

# Windows 控制台友好：控制台已是 UTF-8 或 GBK 时保持原样（改反而乱码），
# 只有编码能力不足（ascii/latin-1）时才切到 UTF-8。
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

SPARQL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKI_REST = "https://zh.wikipedia.org/api/rest_v1/page/summary/"
NE_50M = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "master/geojson/ne_50m_admin_0_countries.geojson")

# 目录归属规则：结构化字段以 Wikidata 为准，几何以 Natural Earth 为准，
# 文本以对应语种 Wikipedia 为准 —— 三者各管各的字段，不互相覆盖。
ISO_TO_QID_FALLBACK = {"CN": "Q148", "FR": "Q142", "US": "Q30"}


# ---------------------------------------------------------------- 基础工具
def log(msg):
    print(msg, flush=True)


def http_get(url, timeout=45, retries=3, accept=None):
    """带重试的 GET，返回 bytes。"""
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
            last = "HTTP %s" % e.code
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        if i < retries - 1:
            time.sleep(2 + i * 2)
    raise RuntimeError("请求失败 %s（%s）" % (url.split("?")[0], last))


def sparql(query):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    raw = http_get(url, accept="application/sparql-results+json")
    return json.loads(raw.decode("utf-8"))


def strip_html(s):
    if not s:
        return None
    s = re.sub(r"<[^>]+>", "", s)
    s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#039;", "'").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", s).strip()


def coord_from_point(p):
    """'Point(103.0 35.0)' -> [lon, lat]"""
    m = re.search(r"Point\(([-\d.eE]+)\s+([-\d.eE]+)\)", p or "")
    if not m:
        return None
    return [round(float(m.group(1)), 4), round(float(m.group(2)), 4)]


def download(url, dest, timeout=90):
    data = http_get(url, timeout=timeout, retries=2)
    if len(data) < 1024:
        raise RuntimeError("文件过小（%d 字节），疑似错误页" % len(data))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def ext_of(url, default=".jpg"):
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".ogg", ".oga", ".mp3", ".wav", ".flac", ".opus"):
        return ".jpg" if ext == ".jpeg" else ext
    return default


# ---------------------------------------------------------------- 1. Wikidata
def fetch_wikidata(iso2, notes):
    log("[1/4] Wikidata …")
    qid = None
    for attempt_qid in ([None] + ([ISO_TO_QID_FALLBACK[iso2]] if iso2 in ISO_TO_QID_FALLBACK else [])):
        if attempt_qid:
            where = "BIND(wd:%s AS ?item)" % attempt_qid
        else:
            where = '?item wdt:P297 "%s".' % iso2
        q = """
SELECT ?item ?iso2 ?iso3 ?coord ?capital ?capitalLabel ?continentLabel ?zhLabel ?enLabel WHERE {
  %s
  OPTIONAL { ?item wdt:P297 ?iso2. }
  OPTIONAL { ?item wdt:P298 ?iso3. }
  OPTIONAL { ?item wdt:P625 ?coord. }
  OPTIONAL { ?item wdt:P36 ?capital. }
  OPTIONAL { ?item wdt:P30 ?continent. }
  OPTIONAL { ?item rdfs:label ?zhLabel. FILTER(lang(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?enLabel. FILTER(lang(?enLabel) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh,en". }
}
LIMIT 8
""" % where
        try:
            res = sparql(q)
        except Exception as e:
            notes.append("Wikidata 实体查询失败：%s" % e)
            return {}
        rows = res.get("bindings", [])
        if rows:
            qid = rows[0]["item"]["value"].rsplit("/", 1)[-1]
            break

    if not qid:
        notes.append("Wikidata 未按 ISO 码找到实体")
        return {}

    def pick(key):
        for r in rows:
            if key in r and r[key]["value"]:
                return r[key]["value"]
        return None

    out = {
        "qid": qid,
        "iso_a2": pick("iso2") or iso2,
        "iso_a3": pick("iso3"),
        "name_zh": pick("zhLabel"),
        "name_en": pick("enLabel"),
        "capital": pick("capitalLabel"),
        "continent": pick("continentLabel"),
        "centroid": coord_from_point(pick("coord")),
    }

    # 语言 P37
    try:
        res = sparql("""
SELECT ?lang ?langLabel WHERE {
  wd:%s wdt:P37 ?lang.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh,en". }
}""" % qid)
        langs = []
        for r in res.get("bindings", []):
            code = r["lang"]["value"].rsplit("/", 1)[-1]
            label = r.get("langLabel", {}).get("value") or code
            langs.append({"code": code, "name_zh": label, "name_local": label,
                          "role": "official", "audio_url": None,
                          "audio_source": None, "audio_status": "pending"})
        out["languages"] = langs
        if not langs:
            notes.append("Wikidata P37 未返回官方语言")
    except Exception as e:
        notes.append("P37 语言查询失败：%s" % e)

    # 发音音频 P443
    try:
        res = sparql("SELECT ?audio WHERE { wd:%s wdt:P443 ?audio. } LIMIT 3" % qid)
        files = []
        for r in res.get("bindings", []):
            v = r["audio"]["value"]
            name = urllib.parse.unquote(v.rsplit("/", 1)[-1])
            if name and name not in files:
                files.append(name)
        out["_pronunciation_files"] = files
    except Exception as e:
        notes.append("P443 发音查询失败：%s" % e)

    # 地标图 P18
    try:
        res = sparql("SELECT ?img WHERE { wd:%s wdt:P18 ?img. } LIMIT 5" % qid)
        names = []
        for r in res.get("bindings", []):
            name = urllib.parse.unquote(r["img"]["value"].rsplit("/", 1)[-1])
            if name and name not in names:
                names.append(name)
        out["_image_files"] = names
    except Exception as e:
        notes.append("P18 图片查询失败：%s" % e)

    log("      qid=%s  首都=%s  坐标=%s  语言=%d  P18=%d  P443=%d"
        % (out["qid"], out["capital"], out["centroid"],
           len(out.get("languages") or []),
           len(out.get("_image_files") or []),
           len(out.get("_pronunciation_files") or [])))
    return out


# ---------------------------------------------------------------- 2. Wikipedia
def fetch_summary(name_zh, notes):
    log("[2/4] Wikipedia 摘要 …")
    if not name_zh:
        notes.append("无中文名，跳过摘要")
        return None
    url = WIKI_REST + urllib.parse.quote(name_zh)
    try:
        d = json.loads(http_get(url, accept="application/json").decode("utf-8"))
    except Exception as e:
        notes.append("Wikipedia 摘要失败：%s" % e)
        return None
    text = (d.get("extract") or "").strip()
    if not text:
        notes.append("Wikipedia 摘要为空")
        return None
    # 压到 300~500 字：优先在句末切，其次硬截
    if len(text) > 500:
        cut = text[:500]
        pos = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
        text = cut[:pos + 1] if pos > 250 else cut.rstrip() + "……"
    log("      摘要 %d 字" % len(text))
    if len(text) < 300:
        notes.append("摘要仅 %d 字，低于 300 字下限，需人工或 LLM 补写" % len(text))
    return {"text": text, "title": d.get("title"), "url": d.get("content_urls", {}).get("desktop", {}).get("page")}


# ---------------------------------------------------------------- 3. Commons
def norm_title(t):
    """Commons 返回的标题会把下划线换成空格，统一成可比较的形式"""
    return (t or "").replace("File:", "").replace("_", " ").strip().lower()


def lookup_meta(info, name):
    if not info:
        return None
    return info.get(norm_title(name))


def commons_imageinfo(files, width=900):
    """批量取 File:xxx 的直链与授权元数据"""
    out = {}
    for i in range(0, len(files), 10):
        chunk = files[i:i + 10]
        params = {
            "action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|mime",
            "titles": "|".join("File:" + f for f in chunk),
        }
        if width:
            params["iiurlwidth"] = str(width)
        url = COMMONS_API + "?" + urllib.parse.urlencode(params)
        try:
            d = json.loads(http_get(url, accept="application/json").decode("utf-8"))
        except Exception:
            continue
        for page in (d.get("query", {}).get("pages", {}) or {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            if not ii.get("url"):
                continue
            meta = ii.get("extmetadata") or {}
            lic = meta.get("LicenseShortName", {}).get("value")
            key = norm_title(page.get("title", ""))
            out[key] = {
                "remote_url": ii.get("thumburl") or ii.get("url"),
                "original_url": ii.get("url"),
                "width": ii.get("thumbwidth") or ii.get("width"),
                "mime": ii.get("mime"),
                "license": strip_html(lic),
                "license_url": meta.get("LicenseUrl", {}).get("value"),
                "artist": strip_html(meta.get("Artist", {}).get("value")),
                "credit": strip_html(meta.get("Credit", {}).get("value")),
                "description": strip_html(meta.get("ImageDescription", {}).get("value")),
            }
    return out


def fetch_assets(iso2, wd, notes):
    log("[3/4] Commons 图片与发音 …")
    slug = iso2.lower()
    img_dir = os.path.join(ROOT, "assets", slug)
    aud_dir = os.path.join(ROOT, "assets", slug)
    images, audio = [], None

    img_files = (wd.get("_image_files") or [])[:3]
    if not img_files:
        notes.append("Wikidata 无 P18 代表图，需人工指定或走 Commons 分类遍历")
    info = commons_imageinfo(img_files) if img_files else {}

    for idx, name in enumerate(img_files, 1):
        meta = lookup_meta(info, name)
        if not meta or not meta.get("remote_url"):
            notes.append("图片 %s 未取到直链，已跳过" % name)
            continue
        if not meta.get("license"):
            notes.append("图片 %s 缺授权字段，按规则丢弃" % name)
            continue
        ext = ext_of(meta["remote_url"])
        local = os.path.join(img_dir, "%02d%s" % (idx, ext))
        rel = "assets/%s/%02d%s" % (slug, idx, ext)
        try:
            size = download(meta["remote_url"], local)
        except Exception as e:
            notes.append("图片 %s 下载失败：%s" % (name, e))
            continue
        images.append({
            "title": "File:" + name,
            "caption": (meta.get("description") or "").split("。")[0][:60] or name,
            "url": rel,
            "thumb_url": rel,
            "remote_url": meta["remote_url"],
            "source": "commons",
            "author": meta.get("artist"),
            "license": meta["license"],
            "license_url": meta.get("license_url"),
            "license_status": "ok",
            "load_verified": True,
            "bytes": size,
        })
        log("      %s  %.0f KB  %s" % (rel, size / 1024, meta["license"]))

    for name in (wd.get("_pronunciation_files") or [])[:1]:
        meta = lookup_meta(commons_imageinfo([name], width=0), name)
        if not meta or not meta.get("original_url"):
            notes.append("发音文件 %s 未取到直链" % name)
            continue
        ext = ext_of(meta["original_url"], ".ogg")
        rel = "assets/%s/pronunciation%s" % (slug, ext)
        try:
            size = download(meta["original_url"], os.path.join(aud_dir, "pronunciation" + ext))
        except Exception as e:
            notes.append("发音下载失败：%s" % e)
            continue
        audio = {
            "url": rel,
            "source": "commons",
            "origin_title": "File:" + name,
            "license": meta.get("license"),
            "license_url": meta.get("license_url"),
            "author": meta.get("artist"),
            "bytes": size,
        }
        log("      %s  %.0f KB" % (rel, size / 1024))

    if not images:
        notes.append("本次未获得任何带授权的地标图")
    if not audio:
        notes.append("Commons 无可用发音，语音走构建期 TTS 兜底（待接）")
    return images, audio


# ---------------------------------------------------------------- 4. 边界
def fetch_geo(iso2, notes):
    log("[4/4] Natural Earth 50m 边界 …（首次约 24MB，慢）")
    cache = os.path.join(ROOT, "geo", "_ne_50m_countries.geojson")
    if not os.path.exists(cache):
        try:
            size = download(NE_50M, cache, timeout=300)
            log("      已下载 Natural Earth（%.0f MB）" % (size / 1048576))
        except Exception as e:
            notes.append("Natural Earth 下载失败：%s" % e)
            return None, None
    with open(cache, encoding="utf-8") as f:
        fc = json.load(f)
    for feat in fc.get("features", []):
        p = feat.get("properties", {})
        codes = {(p.get("ISO_A2") or "").upper(), (p.get("ISO_A2_EH") or "").upper(),
                 (p.get("WB_A2") or "").upper()}
        if iso2.upper() in codes and iso2.upper() not in ("-99", ""):
            name = p.get("NAME_ZH") or p.get("NAME")
            out = os.path.join(ROOT, "geo", "%s.geojson" % iso2.lower())
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                json.dump({"type": "FeatureCollection", "features": [feat]}, f, ensure_ascii=False)
            log("      geo/%s.geojson  <- %s（%s）" % (iso2.lower(), name, p.get("CONTINENT")))
            return "geo/%s.geojson" % iso2.lower(), name
    notes.append("Natural Earth 中未找到 ISO_A2=%s 的要素（微国家常见）" % iso2)
    return None, None


# ---------------------------------------------------------------- 合并输出
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("iso", help="ISO 3166-1 alpha-2，例如 CN")
    ap.add_argument("--geo", action="store_true", help="额外抓 Natural Earth 50m 边界")
    ap.add_argument("--only", choices=["wikidata", "wikipedia", "assets", "geo"], help="只跑某一步")
    args = ap.parse_args()

    iso2 = args.iso.upper()
    data_path = os.path.join(ROOT, "data", "%s.json" % iso2.lower())
    old = {}
    if os.path.exists(data_path):
        with open(data_path, encoding="utf-8") as f:
            old = json.load(f)
        log("读到已有档案 data/%s.json，将保留其中的人工字段（custom_text 等）" % iso2.lower())

    notes = []
    rec = dict(old)

    wd = {}
    if args.only in (None, "wikidata"):
        wd = fetch_wikidata(iso2, notes)
        if wd:
            for k in ("qid", "iso_a2", "iso_a3", "name_zh", "name_en", "capital", "continent"):
                if wd.get(k):
                    rec[k] = wd[k]
            if wd.get("centroid"):
                rec["centroid"] = wd["centroid"]
                rec["centroid_source"] = "wikidata P625"
            if wd.get("languages"):
                # 保留人工补的区域语言（role=regional）
                manual_regional = [l for l in (old.get("languages") or []) if l.get("role") == "regional"]
                rec["languages"] = wd["languages"] + manual_regional

    summ = None
    if args.only in (None, "wikipedia"):
        summ = fetch_summary(rec.get("name_zh") or wd.get("name_zh"), notes)
        if summ:
            rec["summary_text"] = summ["text"]
            rec["summary_source"] = {"source": "wikipedia_rest", "url": summ.get("url"),
                                     "title": summ.get("title"), "chars": len(summ["text"])}

    if args.only in (None, "assets"):
        images, audio = fetch_assets(iso2, wd, notes)
        if images:
            rec["landmark_images"] = images
            rec["image_license"] = images[0]["license"]
        if audio:
            rec["audio_url"] = audio["url"]
            rec["audio_source"] = "commons"
            rec["audio_meta"] = audio
            for l in rec.get("languages") or []:
                if l.get("role") == "official":
                    l["audio_url"] = audio["url"]
                    l["audio_source"] = "commons"
                    l["audio_status"] = "ok"
                    break

    if args.geo or args.only == "geo":
        geo_rel, geo_name = fetch_geo(iso2, notes)
        if geo_rel:
            rec["geometry"] = geo_rel
            rec["geometry_status"] = "naturalearth_50m"
            rec["geometry_name"] = geo_name

    # 清掉中间字段，不落盘
    for k in ("_image_files", "_pronunciation_files"):
        rec.pop(k, None)

    rec["schema_version"] = "0.1"
    rec["collected_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    rec["collector"] = "scripts/collect.py v0.1"
    rec["needs_review"] = bool(notes) or bool(rec.get("needs_review"))
    rec["review_notes"] = notes if notes else ["本次采集各字段均已取到，待人工复核内容质量"]

    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # 同步 index.json 的入口卡信息
    idx_path = os.path.join(ROOT, "data", "index.json")
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
        for c in idx.get("countries", []):
            if c.get("iso_a2") == iso2:
                any_img = bool(rec.get("landmark_images"))
                c["name_zh"] = rec.get("name_zh") or c.get("name_zh")
                c["name_en"] = rec.get("name_en") or c.get("name_en")
                c["name_local"] = rec.get("name_local") or rec.get("name_zh") or c.get("name_local")
                c["continent"] = rec.get("continent") or c.get("continent")
                c["capital"] = rec.get("capital") or c.get("capital")
                c["centroid"] = rec.get("centroid") or c.get("centroid")
                c["thumb"] = rec["landmark_images"][0]["thumb_url"] if any_img else None
                c["modalities"] = {
                    "image": any_img,
                    "audio": bool(rec.get("audio_url")),
                    "text": bool(rec.get("summary_text")),
                    "coords": bool(rec.get("centroid")),
                    "geometry": bool(rec.get("geometry")),
                }
                n = sum(1 for v in c["modalities"].values() if v)
                c["status"] = "partial" if n < 5 else "complete"
        idx["updated_at"] = datetime.now(TZ).date().isoformat()
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
            f.write("\n")
        log("已同步 data/index.json 入口卡")

    log("\n===== 完成 =====")
    log("档案：data/%s.json" % iso2.lower())
    filled = [k for k in ("qid", "iso_a3", "name_zh", "capital", "continent", "centroid",
                          "languages", "landmark_images", "image_license", "summary_text",
                          "custom_text", "audio_url", "geometry") if rec.get(k)]
    log("非空字段 %d / 13" % len(filled))
    log("图片 %d 张，音频 %s" % (len(rec.get("landmark_images") or []),
                              "有" if rec.get("audio_url") else "无"))
    if notes:
        log("\n待复核（%d 条）：" % len(notes))
        for n in notes:
            log("  · " + n)
    log("\n下一步：git add 后推送，或告诉我 JSON 已生成，我来核对并接前端。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n已中断")
    except Exception as e:
        log("\n!! 采集失败：%s: %s" % (type(e).__name__, e))
        log("   常见原因：① 代理未开 ② 目标站临时不可达 ③ ISO 码写错")
        sys.exit(1)
