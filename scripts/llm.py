#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DeepSeek 调用统一封装（构建期使用，key 只从环境变量读）。

设计要点
--------
1. **key 绝不写进代码、绝不进仓库**。只读环境变量 ``DEEPSEEK_API_KEY``。
   前端页面永不接触 key —— 静态站一旦明文放 key，F12 就能看到，公开仓库更是
   直接被爬虫扫走。本项目的大模型调用全部发生在构建期（你这台机器上跑脚本），
   产物落成 JSON，线上页面只读 JSON，因此断网也能演示。
2. **每次调用都记账**，写入 ``logs/llm_calls.jsonl``（只记元数据，不记正文）。
   这份日志进仓库，是「大模型使用次数」的举证材料，也是 CI 的统计来源。
3. **失败可重试**，429/5xx 退避；4xx（除 429）直接抛，因为那是请求本身错了。
4. 模型名默认 ``deepseek-flash``。旧名 ``deepseek-chat`` / ``deepseek-reasoner``
   已于 2026-07-24 退役，写旧名会 400。
5. **默认关闭 thinking**。实测 DeepSeek-V4 默认开启思考，reasoning_tokens 会占用
   max_tokens 配额：同一句翻译，``max_tokens=64`` 且开思考时推理吃掉全部 64 个，
   返回**空 content**（finish_reason=length）；关闭思考后只花 7 个 token 就给出结果。
   抽取/翻译/质检这类任务不需要长链条推理，关掉既省钱又快 20 倍。
   复杂判断（如实体消歧有多个候选时要权衡）可显式传 ``thinking=True``。

用法
----
    export DEEPSEEK_API_KEY=sk-xxx
    python scripts/llm.py --selftest          # 连通性 + 模型可用性
    python scripts/llm.py --stats             # 累计调用次数 / token / 场景分布

    # 代码里调用
    from llm import chat, chat_json
    chat("用一句话介绍中国", scene="demo")
    chat_json("把下面内容抽成 json：…", scene="extract")
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys

# 控制台可能是 cp936（Windows cmd 默认），打不出的字符用 ? 代替，别让整段崩掉。
# 之前 collect.py 在连不上某个站时打印一个 ✗ 就 UnicodeEncodeError 退出，
# 看起来像"采集失败"，其实连抓取都还没开始。
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Windows 控制台友好：编码能力不足时才切 UTF-8
try:
    enc = (sys.stdout.encoding or "").lower()
    if enc not in ("utf-8", "utf8", "cp936", "gbk", "gb2312", "cp65001"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "llm_calls.jsonl")

# .env（已在 .gitignore）里的 KEY=VALUE 先灌进环境变量，命令行里的真实环境变量优先。
# 之前这里只有注释说"可以写进 .env"，实际没有任何加载器 —— 写了并不生效。
try:
    from envfile import load as _load_env
except ImportError:                                  # 被当模块导入时
    from scripts.envfile import load as _load_env
_load_env()

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
# 备选：deepseek-v4-pro（更强、更贵）。抽取类任务用 flash 足够。
TIMEOUT = int(os.environ.get("DEEPSEEK_TIMEOUT", "120"))


class LLMError(RuntimeError):
    pass


def _key() -> str:
    k = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not k:
        raise LLMError(
            "未设置 DEEPSEEK_API_KEY。\n"
            "  临时生效（当前窗口）：  export DEEPSEEK_API_KEY=sk-xxx\n"
            "  或者写进 .env（已在 .gitignore 里，不会入库）"
        )
    return k


def _log(rec: dict) -> None:
    """追加一条调用记录。只存元数据：不含 prompt 正文、不含 key。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    rec.setdefault("ts", datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _post(payload: dict, retries: int = 3) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last = None
    for i in range(retries + 1):
        req = urllib.request.Request(BASE_URL + "/chat/completions", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + _key())
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            # 429 与 5xx 可重试；其余 4xx 是请求本身有问题，重试无意义
            if e.code == 429 or 500 <= e.code < 600:
                last = "HTTP %d: %s" % (e.code, detail)
                time.sleep((2 ** i) + random.random())
                continue
            raise LLMError("HTTP %d: %s" % (e.code, detail))
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(e)
            time.sleep((2 ** i) + random.random())
    raise LLMError("重试 %d 次仍失败：%s" % (retries, last))


def chat(
    prompt: str,
    system: str = "你是一个严谨的中文数据工程助手，回答简洁准确。",
    scene: str = "general",
    json_mode: bool = False,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    thinking: bool = False,
    note: str = "",
) -> str:
    """单轮对话，返回文本。``scene`` 用于统计口径（哪一类用途）。

    ``thinking`` 默认 False —— 抽取/翻译/质检不需要长链条推理，开着会让
    reasoning_tokens 吃掉 max_tokens，短任务直接返回空串。
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "thinking": {"type": "enabled" if thinking else "disabled"},
    }
    if json_mode:
        # DeepSeek 的 JSON Output 要求 prompt 里出现 "json" 字样，否则可能报错
        if "json" not in prompt.lower():
            payload["messages"][-1]["content"] = prompt + "\n\n请只输出 json，不要解释。"
        payload["response_format"] = {"type": "json_object"}

    t0 = time.time()
    try:
        resp = _post(payload)
    except LLMError as e:
        _log({"scene": scene, "model": MODEL, "ok": False, "error": str(e)[:200],
              "latency_ms": int((time.time() - t0) * 1000), "note": note,
              "prompt_sha": hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]})
        raise

    usage = resp.get("usage") or {}
    choice = (resp.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content") or "").strip()
    reason_tok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    finish = choice.get("finish_reason")

    rec = {
        "scene": scene,
        "model": resp.get("model") or MODEL,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": reason_tok or None,
        "total_tokens": usage.get("total_tokens"),
        "latency_ms": int((time.time() - t0) * 1000),
        "prompt_sha": hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12],
        "note": note,
    }

    # 空响应必须显式报错，不能静默返回空串 —— 下游把空串写进 JSON 是最难查的一类错。
    # 实测成因：thinking 开启时 reasoning_tokens 独占 max_tokens，finish_reason=length。
    if not text:
        rec["ok"] = False
        rec["error"] = "空响应 finish=%s reasoning=%d" % (finish, reason_tok)
        _log(rec)
        raise LLMError(
            "模型返回空内容（finish_reason=%s，其中推理 token %d）。"
            "多半是 max_tokens 被思考过程吃光，或该任务应关闭 thinking。" % (finish, reason_tok))

    rec["ok"] = True
    _log(rec)
    return text


def chat_json(prompt: str, **kw) -> dict:
    """要求模型输出 JSON 并解析。解析失败时抛错（附原文前 300 字）。"""
    raw = chat(prompt, json_mode=True, **kw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 偶尔会包一层 ```json ... ```
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("```")[1]
            if s.lstrip().lower().startswith("json"):
                s = s.lstrip()[4:]
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            raise LLMError("模型返回不是合法 JSON：%s" % raw[:300])


# ------------------------------------------------------------------ 自检与统计
def selftest() -> int:
    print("== DeepSeek 连通性自检 ==")
    print("  base_url :", BASE_URL)
    print("  model    :", MODEL)
    k = os.environ.get("DEEPSEEK_API_KEY") or ""
    print("  api_key  :", ("已设置 (%s…%s, %d 字符)" % (k[:5], k[-4:], len(k))) if k else "**未设置**")
    if not k:
        print("\n  请先 export DEEPSEEK_API_KEY=sk-xxx")
        return 2

    ok = 0
    try:
        t0 = time.time()
        out = chat("用一句不超过 20 字的中文回答：中国的首都是哪里？",
                   scene="selftest", max_tokens=64, note="连通性")
        print("  ① 纯文本   : [ok] %dms  %r" % (int((time.time() - t0) * 1000), out[:40]))
        ok += 1
    except LLMError as e:
        print("  ① 纯文本   : [x]", e)
        return 1

    try:
        d = chat_json('把下面信息抽取成 json，键为 capital 与 continent：'
                      '中国位于亚洲，首都是北京。', scene="selftest", max_tokens=128,
                      note="JSON 模式")
        print("  ② JSON 模式: [ok]", d)
        ok += 1
    except LLMError as e:
        print("  ② JSON 模式: [x]", e)

    try:
        # 中文图注翻译这类短任务，验证小 token 也能收住
        out = chat("把 'West facade of the Cour Carrée, Louvre Palace, Paris' "
                   "翻译成中文专有名词，只输出译名。", scene="selftest",
                   max_tokens=64, note="翻译")
        print("  ③ 翻译     : [ok]", out[:50])
        ok += 1
    except LLMError as e:
        print("  ③ 翻译     : [x]", e)

    print("\n%d/3 通过。日志已写入 %s" % (ok, os.path.relpath(LOG_FILE, ROOT)))
    return 0 if ok == 3 else 1


def stats() -> int:
    if not os.path.exists(LOG_FILE):
        print("还没有调用记录（%s 不存在）" % os.path.relpath(LOG_FILE, ROOT))
        return 1
    rows = [json.loads(l) for l in open(LOG_FILE, encoding="utf-8") if l.strip()]
    ok = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if not r.get("ok")]
    scenes: dict[str, int] = {}
    for r in ok:
        scenes[r.get("scene", "?")] = scenes.get(r.get("scene", "?"), 0) + 1
    ptok = sum(r.get("prompt_tokens") or 0 for r in ok)
    ctok = sum(r.get("completion_tokens") or 0 for r in ok)
    rtok = sum(r.get("reasoning_tokens") or 0 for r in ok)
    lat = [r.get("latency_ms") or 0 for r in ok]

    print("== 大模型调用台账 ==")
    print("  实际网络调用 : %d 次（成功 %d / 失败 %d）" % (len(rows), len(ok), len(bad)))
    print("  使用场景数   : %d 类" % len(scenes))
    print("  prompt token : %s" % format(ptok, ","))
    print("  输出 token   : %s（其中思考 %s）" % (format(ctok, ","), format(rtok, ",")))
    if ctok and rtok:
        print("  思考占比     : %.0f%%（关闭 thinking 后这部分省下）" % (rtok * 100 / ctok))
    if lat:
        print("  平均延迟     : %d ms（最慢 %d ms）" % (sum(lat) // len(lat), max(lat)))
    if rows:
        days = sorted({(r.get("ts") or "")[:10] for r in rows if r.get("ts")})
        print("  跨天数       : %d 天（%s ~ %s）" % (len(days), days[0], days[-1]))
    # 按峰值价保守估算：入 $0.3/M、出 $1.2/M（off-peak 是半价）
    cost = ptok / 1e6 * 0.3 + ctok / 1e6 * 1.2
    print("  累计花费     : 约 $%.2f（按峰值价估算，实际更低）" % cost)
    print("  场景分布     :")
    for s, n in sorted(scenes.items(), key=lambda x: -x[1]):
        print("     %-16s %d 次" % (s, n))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="DeepSeek 调用封装")
    ap.add_argument("--selftest", action="store_true", help="连通性 + JSON 模式自检")
    ap.add_argument("--stats", action="store_true", help="打印调用台账")
    ap.add_argument("--ask", help="临时问一句（调试用）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.stats:
        return stats()
    if a.ask:
        print(chat(a.ask, scene="adhoc"))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
