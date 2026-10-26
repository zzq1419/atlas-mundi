# -*- coding: utf-8 -*-
"""华为云 FunctionGraph 函数：寰宇图志检索 API。

与前端 index.html 里的检索算法**同一套逻辑**（中文 2-gram + BM25 + 停用词 + 双阈值），
所以同一句查询在本地和云端应该返回同样的结果 —— 这条在离线测试里逐条比对了。

为什么需要这个 API：前端检索是本地算的（快、可离线），但那样只能服务这一个页面。
把同一套逻辑封成 Serverless 接口后，任何客户端（小程序、命令行、别的系统）都能查。
两种形态并存：页面用本地，外部调用走 API。

只依赖 Python 标准库，函数包 = handler.py + search.json，约 15KB。
"""

import json
import math
import os
import re

CJK = re.compile(r"[\u3400-\u9fff]")
ALNUM = re.compile(r"[a-z0-9]")

# 与 index.html 里的 STOP 表保持一致（改一处要同步另一处）
STOP = set("""
哪里 里能 能看 什么 怎么 哪些 哪个 多少 哪儿 有什 么地 么语 么节 么样 么东
有哪 些地 请问 一下 告诉 知道 我想 想要 是否 可以 应该 这个 那个
这些 那些 是什 为什 一个 有些 有没 没有 是不 不是
""".split())

MIN_SCORE = 1.5
REL_RATIO = 0.35

_DATA = None


def _data():
    """懒加载索引，函数实例复用期间只读一次文件。"""
    global _DATA
    if _DATA is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "search.json")
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        _DATA = _build(raw.get("docs") or [])
    return _DATA


def tokenize(text):
    """中文切 2-gram，英文数字按连续串切。不分词、不引词典。"""
    s = str(text or "").lower()
    toks = []
    buf = []
    mode = None

    def flush_cjk(chars):
        if not chars:
            return
        if len(chars) == 1:
            toks.append(chars[0])
            return
        for i in range(len(chars) - 1):
            toks.append(chars[i] + chars[i + 1])

    def flush_word(chars):
        if len(chars) >= 2:
            toks.append("".join(chars))

    for ch in s:
        if CJK.match(ch):
            m = "c"
        elif ALNUM.match(ch):
            m = "a"
        else:
            m = None
        if m != mode:
            if mode == "c":
                flush_cjk(buf)
            elif mode == "a":
                flush_word(buf)
            buf = []
            mode = m
        if m:
            buf.append(ch)
    if mode == "c":
        flush_cjk(buf)
    elif mode == "a":
        flush_word(buf)
    return toks


def _build(docs):
    postings = {}
    df = {}
    lens = []
    for i, d in enumerate(docs):
        toks = tokenize(d.get("index_text"))
        lens.append(len(toks) or 1)
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        for t, n in tf.items():
            postings.setdefault(t, {})[i] = n
            df[t] = df.get(t, 0) + 1
    n = len(docs) or 1
    return {
        "docs": docs,
        "postings": postings,
        "df": df,
        "lens": lens,
        "avgdl": (sum(lens) / n) if lens else 1.0,
        "N": len(docs),
    }


def search(query, topk=5):
    idx = _data()
    if not idx["N"]:
        return []
    k1, b = 1.5, 0.75
    score = {}
    for t in tokenize(query):
        if t in STOP:
            continue
        pl = idx["postings"].get(t)
        if not pl:
            continue
        n = idx["df"].get(t, 0)
        idf = math.log(1 + (idx["N"] - n + 0.5) / (n + 0.5))
        for i, tf in pl.items():
            dl = idx["lens"][i]
            score[i] = score.get(i, 0.0) + idf * (tf * (k1 + 1)) / (
                tf + k1 * (1 - b + b * dl / idx["avgdl"]))

    hits = [(idx["docs"][i], s) for i, s in score.items() if s > MIN_SCORE]
    hits.sort(key=lambda x: -x[1])
    if not hits:
        return []
    floor = hits[0][1] * REL_RATIO
    hits = [h for h in hits if h[1] >= floor]
    return hits[:topk]


def _extract_query(event):
    """兼容三种触发格式：直调、API 网关、HTTP 函数。"""
    if not isinstance(event, dict):
        return str(event or "").strip()

    for k in ("q", "query", "keyword"):
        v = event.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    qs = event.get("queryStringParameters") or event.get("queryString") or {}
    if isinstance(qs, dict):
        for k in ("q", "query"):
            v = qs.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    body = event.get("body")
    if body:
        try:
            obj = json.loads(body) if isinstance(body, str) else body
        except Exception:
            obj = None
        if isinstance(obj, dict):
            for k in ("q", "query"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        elif isinstance(body, str) and len(body.strip()) < 200:
            return body.strip()

    return ""


def _reply(payload, code=200):
    return {
        "statusCode": code,
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Cache-Control": "no-cache",
        },
        "body": json.dumps(payload, ensure_ascii=False),
    }


def handler(event, context):
    """FunctionGraph 入口。"""
    # OPTIONS 预检（浏览器跨域会先发这个）
    if isinstance(event, dict) and str(event.get("httpMethod") or "").upper() == "OPTIONS":
        return _reply({"ok": True})

    q = _extract_query(event)
    idx = _data()

    if not q:
        return _reply({
            "ok": False,
            "usage": "GET ?q=你的问题  或  POST {\"q\": \"你的问题\"}",
            "docs": idx["N"],
            "示例": "?q=哪里能看长城",
        }, 400)

    if len(q) < 2:
        return _reply({"ok": False, "error": "查询至少 2 个字符"}, 400)

    hits = search(q, topk=5)
    out = {
        "ok": True,
        "query": q,
        "count": len(hits),
        "results": [
            {
                "country": d.get("name"),
                "iso": d.get("iso"),
                "kind": d.get("kind"),
                "q": d.get("q"),
                "a": d.get("a"),
                "tags": d.get("tags") or [],
                "score": round(s, 3),
            }
            for d, s in hits
        ],
        "engine": "bm25 + zh-2gram",
        "corpus_docs": idx["N"],
    }
    # 空结果要给出可执行的原因，而不是干巴巴一个空数组。
    # 调用方需要能区分「知识库没这条」和「你查询写错了」。
    if not hits:
        out["note"] = ("知识库无匹配内容（语料仅 %d 条，覆盖 CN/FR/US 三国）。"
                       "这不是接口故障 —— 换个说法或问三国相关的内容。" % idx["N"])
    return _reply(out)
