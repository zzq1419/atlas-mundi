#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把各国档案里的问答对与简介合并成一份前端可检索的索引。

为什么在构建期生成而不是前端现算：
- 前端只做**检索**（2-gram + BM25），不做生成，所以断网也能用；
- 生成性工作全部由大模型在构建期完成，key 不进浏览器；
- 数据量小（3 国 25 条），整份索引约 20KB，一次请求即可。

索引结构（data/search.json）：
    {"built_at", "doc_count", "docs": [{id, iso, name, kind, q, a, tags, index_text}]}

``index_text`` 是给检索用的拼接文本（问题 + 标签 + 国名），
``a`` 只用于展示 —— 若把答案也计入检索域，长答案会稀释关键词权重。
"""

from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "search.json")


def load_records() -> list[dict]:
    recs = []
    for p in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        name = os.path.basename(p)
        if name in ("index.json", "landmarks.json", "search.json"):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                r = json.load(f)
        except Exception:
            continue
        # 只认国家档案：landmarks.json 这类配置没有 iso_a2（已踩过三次）
        if r.get("iso_a2"):
            recs.append(r)
    return recs


def build() -> dict:
    docs = []
    for r in load_records():
        iso = r["iso_a2"]
        name = r.get("name_zh") or iso
        facets = r.get("custom_facets") or {}
        kws = [x.get("v") for x in (facets.get("keywords") or []) if x.get("v")]
        marks = [i.get("caption_zh") or i.get("caption")
                 for i in (r.get("landmark_images") or [])]

        # 1) 简介类文档：问答覆盖不到的开放提问靠它兜底
        docs.append({
            "id": "%s-brief" % iso.lower(),
            "iso": iso,
            "name": name,
            "kind": "brief",
            "q": "%s 简介" % name,
            "a": (r.get("summary_text") or "")[:400],
            "tags": kws,
            "index_text": " ".join([name, r.get("name_en") or "", r.get("name_local") or "",
                                    r.get("capital") or "", r.get("continent") or "",
                                    " ".join(kws), " ".join(marks),
                                    " ".join(l.get("name_zh") or ""
                                             for l in (r.get("languages") or []))]),
        })

        # 2) 问答文档：主要检索单元
        for i, qa in enumerate(r.get("knowledge_qa") or [], 1):
            docs.append({
                "id": "%s-q%d" % (iso.lower(), i),
                "iso": iso,
                "name": name,
                "kind": "qa",
                "q": qa.get("q") or "",
                "a": qa.get("a") or "",
                "tags": qa.get("tags") or [],
                "index_text": " ".join([name, qa.get("q") or "", " ".join(qa.get("tags") or [])]),
            })

    return {
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "doc_count": len(docs),
        "schema": 1,
        "note": "检索用 2-gram + BM25，纯前端计算；答案由大模型在构建期生成，页面不调 API",
        "docs": docs,
    }


def main() -> int:
    idx = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1, separators=(",", ":"))
        f.write("\n")

    size = os.path.getsize(OUT)
    qa_n = sum(1 for d in idx["docs"] if d["kind"] == "qa")
    brief_n = sum(1 for d in idx["docs"] if d["kind"] == "brief")
    isos = sorted({d["iso"] for d in idx["docs"]})

    print("索引已生成 data/search.json")
    print("  文档数  %d（问答 %d + 简介 %d）" % (idx["doc_count"], qa_n, brief_n))
    print("  覆盖    %s" % "、".join(isos))
    print("  体积    %.1f KB" % (size / 1024))
    if not qa_n:
        print("  ⚠ 没有问答对：先跑 python scripts/llm_tasks.py --run all --only qa --apply")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
