#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 ISO 码解析成 Wikidata QID（全量国家），并顺带解析语言代码。

为什么需要这一步
----------------
`collect.py` 原来靠一张手写的 ISO→QID 表（只有 CN/FR/US）。要覆盖 200 多个国家，
手写不可行；而 Wikidata 的 SPARQL 查询在部分代理下会返回 200 + 空 bindings，
极难排查（collect.py 的注释里记着这个坑）。所以这里走 REST + Action API：

    1. wbsearchentities（中文名 → 候选 QID）
    2. Special:EntityData 取实体，**用 P297（ISO 3166-1 alpha-2）校验**
    3. 校验不过就换英文名再搜一轮
    4. 都不行 → 记进 data/_ids_unresolved.json，人工用 --set 补

产物 data/_ids.json：

    {
      "JP": {"qid": "Q17", "name_zh": "日本", "via": "zh", "verified": true},
      ...
      "_langs": {"Q5287": {"c1": "ja", "c3": "jpn"}}
    }

用法
----
    python scripts/resolve_ids.py                 # 全量解析（可重复跑，已解析的跳过）
    python scripts/resolve_ids.py --limit 20      # 先试 20 个
    python scripts/resolve_ids.py --only JP EG    # 只补这几个
    python scripts/resolve_ids.py --set XK=Q1246  # 手工指定（冲突/属地常用）
    python scripts/resolve_ids.py --report        # 只看当前进度和未解析清单

代理：默认读环境变量 HTTPS_PROXY / HTTP_PROXY，也可以 --proxy http://127.0.0.1:7890
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    enc = (sys.stdout.encoding or "").lower()
    if enc not in ("utf-8", "utf8", "cp936", "gbk", "gb2312", "cp65001"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "AtlasMundi/0.2 (course project; contact: 2036829270@qq.com)"

META = os.path.join(ROOT, "geo", "meta.json")
IDS = os.path.join(ROOT, "data", "_ids.json")
UNRESOLVED = os.path.join(ROOT, "data", "_ids_unresolved.json")

WD_API = "https://www.wikidata.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/%s.json"

# 国家 / 主权国家 / 共和国 / 王国 / 属地 —— 用来给候选打分，不做硬性要求
STATE_QIDS = {"Q6256", "Q3624078", "Q7275", "Q3024240", "Q179164"}

OPENED = {"opener": None}


def opener():
    if OPENED["opener"] is None:
        OPENED["opener"] = urllib.request.build_opener()
    return OPENED["opener"]


def set_proxy(url: str | None):
    if not url:
        return
    h = urllib.request.ProxyHandler({"http": url, "https": url})
    OPENED["opener"] = urllib.request.build_opener(h)
    print("使用代理：%s" % url)


def http_json(url, timeout=40, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json"})
            with opener().open(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = "HTTP %s" % e.code
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 + i * 3)
                continue
            raise
        except Exception as e:            # 超时 / 连接被重置 / 代理未开
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(1.5 + i * 2)
    raise RuntimeError(last or "unknown")


def qs(**kw):
    return urllib.parse.urlencode(kw)


def search_entities(term, lang, limit=8):
    url = WD_API + "?" + qs(action="wbsearchentities", search=term, language=lang,
                            uselang=lang, type="item", limit=limit, format="json",
                            origin="*")
    d = http_json(url)
    return d.get("search") or []


def entity_claims_batch(qids):
    """一次取多个实体的 claims。

    用 wbgetentities 而不是 Special:EntityData：后者单个实体就 2MB 左右，
    逐个候选拉会把解析阶段拖成几分钟；批量接口一次最多 50 个，快一个量级。
    """
    out = {}
    qids = [q for q in dict.fromkeys(qids) if q]
    for i in range(0, len(qids), 20):
        chunk = qids[i:i + 20]
        url = WD_API + "?" + qs(action="wbgetentities", ids="|".join(chunk),
                                props="claims", format="json", origin="*")
        try:
            d = http_json(url)
        except Exception:
            continue
        for qid, ent in (d.get("entities") or {}).items():
            out[qid] = ent.get("claims") or {}
    return out


def claim_ids(claims, prop):
    out = []
    for c in claims.get(prop) or []:
        dv = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
        if isinstance(dv, dict) and dv.get("id"):
            out.append(dv["id"])
    return out


def claim_strs(claims, prop):
    out = []
    for c in claims.get(prop) or []:
        dv = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
        if isinstance(dv, str):
            out.append(dv)
    return out


def labels_of(qids):
    """批量取中文标签，50 个一批。"""
    out = {}
    qids = [q for q in dict.fromkeys(qids) if q]
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        url = WD_API + "?" + qs(action="wbgetentities", ids="|".join(chunk),
                                props="labels", languages="zh-cn|zh-hans|zh|en",
                                format="json", origin="*")
        d = http_json(url)
        for qid, ent in (d.get("entities") or {}).items():
            for key in ("zh-cn", "zh-hans", "zh", "en"):
                v = ((ent.get("labels") or {}).get(key) or {}).get("value")
                if v:
                    out[qid] = v
                    break
    return out


def resolve_one(iso, name_zh, name_en):
    """返回 (qid, via, verified) 或 (None, reason, False)。"""
    notes = []
    for lang, term in (("zh", name_zh), ("en", name_en)):
        if not term:
            continue
        try:
            cands = search_entities(term, lang)
        except Exception as e:
            notes.append("%s 搜索失败：%s" % (lang, e))
            continue
        ids = [c.get("id") for c in cands[:6] if (c.get("id") or "").startswith("Q")]
        claims_all = entity_claims_batch(ids)
        best = None
        for qid in ids:
            claims = claims_all.get(qid) or {}
            if not claims:
                continue
            a2 = [x.upper() for x in claim_strs(claims, "P297")]
            a3 = [x.upper() for x in claim_strs(claims, "P298")]
            inst = set(claim_ids(claims, "P31"))
            score = 0
            if iso.upper() in a2:
                score += 100
            if a2 and iso.upper() not in a2:
                score -= 60          # 明确给了别的 ISO，基本可以排除
            if inst & STATE_QIDS:
                score += 25
            score += 5 if lang == "zh" else 0
            if score > (best[0] if best else -999):
                best = (score, qid, bool(iso.upper() in a2))
        if best and best[0] >= 100:
            return best[1], lang, True
        if best and best[0] >= 25 and not notes:
            # 有国家/主权国家特征但缺 P297：接受，但标记未校验
            notes.append("%s 匹配到 %s（无 P297，未校验）" % (lang, best[1]))
            return best[1], lang, False
    return None, "；".join(notes) or "无候选", False


def resolve_langs(ids):
    """把 P37 的语言 QID 解析成 ISO 639 代码（P218 两字母 / P219 三字母）。"""
    need = set()
    for iso, rec in ids.items():
        if iso.startswith("_"):
            continue
        for q in rec.get("lang_qids") or []:
            if q not in (ids.get("_langs") or {}):
                need.add(q)
    if not need:
        return 0
    langs = ids.setdefault("_langs", {})
    qids = [q for q in need if q]
    done = 0
    for i in range(0, len(qids), 40):
        chunk = qids[i:i + 40]
        url = WD_API + "?" + qs(action="wbgetentities", ids="|".join(chunk),
                                props="claims", format="json", origin="*")
        try:
            d = http_json(url)
        except Exception as e:
            print("  ! 语言批量解析失败：%s" % e)
            continue
        for qid, ent in (d.get("entities") or {}).items():
            cl = ent.get("claims") or {}
            c1 = (claim_strs(cl, "P218") or [""])[0]
            c3 = (claim_strs(cl, "P219") or [""])[0]
            langs[qid] = {"c1": c1, "c3": c3}
            done += 1
    return done


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="只处理这些 ISO")
    ap.add_argument("--limit", type=int, default=0, help="最多处理多少个（先试水）")
    ap.add_argument("--set", action="append", default=[], metavar="ISO=QID",
                    help="手工指定，可重复：--set XK=Q1246")
    ap.add_argument("--proxy", help="如 http://127.0.0.1:7890")
    ap.add_argument("--report", action="store_true", help="只打印现状")
    ap.add_argument("--sleep", type=float, default=0.35, help="每个国家之间的间隔秒数")
    a = ap.parse_args()

    set_proxy(a.proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))

    meta = load(META, {})
    ids = load(IDS, {})
    unresolved = load(UNRESOLVED, {})
    if not meta:
        print("缺 geo/meta.json，先跑 scripts/build_countries.py")
        return 1

    for pair in a.set:
        if "=" not in pair:
            continue
        iso, qid = pair.split("=", 1)
        iso, qid = iso.strip().upper(), qid.strip()
        ids[iso] = {"qid": qid, "name_zh": (meta.get(iso) or {}).get("n"),
                    "via": "manual", "verified": False}
        unresolved.pop(iso, None)
        print("手工指定 %s → %s" % (iso, qid))

    if a.report:
        have = [k for k in ids if not k.startswith("_")]
        print("已解析 %d / 目标 %d" % (len(have), len(meta)))
        if unresolved:
            print("\n未解析 %d 个：" % len(unresolved))
            for iso, why in sorted(unresolved.items())[:40]:
                print("  %-3s %s  ← %s" % (iso, (meta.get(iso) or {}).get("n", "?"), why))
        return 0

    todo = sorted(meta.keys())
    if a.only:
        want = {x.upper() for x in a.only}
        todo = [x for x in todo if x.upper() in want]
    todo = [x for x in todo if x not in ids]
    if a.limit:
        todo = todo[:a.limit]

    print("待解析 %d 个（已有 %d 个）" % (len(todo), len(ids)))
    ok = fail = 0
    for n, iso in enumerate(todo, 1):
        m = meta.get(iso) or {}
        try:
            qid, via, verified = resolve_one(iso, m.get("n"), m.get("en"))
        except Exception as e:
            qid, via, verified = None, "%s: %s" % (type(e).__name__, e), False
        if qid:
            ids[iso] = {"qid": qid, "name_zh": m.get("n"), "via": via, "verified": verified}
            unresolved.pop(iso, None)
            ok += 1
            print("[%d/%d] %-3s %-8s → %-9s %s%s"
                  % (n, len(todo), iso, m.get("n", ""), qid, via,
                     "" if verified else "  (未校验)"))
            try:
                cl = entity_claims_batch([qid]).get(qid) or {}
                lq = claim_ids(cl, "P37")
                if lq:
                    ids[iso]["lang_qids"] = lq[:4]
            except Exception:
                pass
        else:
            fail += 1
            unresolved[iso] = via
            print("[%d/%d] %-3s %-8s ✗ %s" % (n, len(todo), iso, m.get("n", ""), via))
        if n % 10 == 0:
            save(IDS, ids)
            save(UNRESOLVED, unresolved)
        time.sleep(a.sleep)

    save(IDS, ids)
    save(UNRESOLVED, unresolved)
    print("\n解析完成：成功 %d，失败 %d" % (ok, fail))

    n = resolve_langs(ids)
    save(IDS, ids)
    print("语言代码解析 %d 个（P218/P219）" % n)
    if fail:
        print("\n失败的可以：① 再跑一次；② python scripts/resolve_ids.py --set XK=Q1246 手工补")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
