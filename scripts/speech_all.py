#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给一个国家生成多语种语音（句子由大模型写，音由 Edge TTS 合成）。

为什么不是简单念国名
--------------------
念两三个字，播放条一闪就没了，演示时根本看不出"这里有语音模态"。
中法美三国的模板是「你好，欢迎来到X。首都是Y。」——5~6 秒，刚好能听清。
250 个国家不可能手写这套句子，所以让大模型按国家+首都生成，
并要求同时给出简体中文译文（卡片上要显示"原文 + 中文"两行）。

音色怎么选
----------
不维护手写音色表（edge 有 300+ 音色，手写必然漏）。启动时拉一次
`edge_tts.list_voices()`，按语言代码匹配 Locale：
    ja  -> ja-JP-NanamiNeural（优先同区域 + 女声）
    yue -> zh-HK-HiuMaanNeural（粤语是中文语族里的特例，单独映射）
查不到音色的语种明确跳过并在 review_notes 留痕，绝不用邻近语种硬读。

用法
----
    python scripts/speech_all.py JP            # 单个
    python scripts/speech_all.py --all         # data/ 下全部档案
    python scripts/speech_all.py JP --force    # 已有音频也重做
    python scripts/speech_all.py --voices ja   # 看看某语言有哪些音色

依赖：pip install edge-tts（key 不需要）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

try:
    enc = (sys.stdout.encoding or "").lower()
    if enc not in ("utf-8", "utf8", "cp936", "gbk", "gb2312", "cp65001"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
META = os.path.join(ROOT, "geo", "meta.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 语言代码 -> 固定音色（只处理"代码匹配不到"的特例，常规情况自动匹配）
VOICE_PIN = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "cmn": "zh-CN-XiaoxiaoNeural",
    "yue": "zh-HK-HiuMaanNeural",
    "en": "en-US-AriaNeural",
    "fr": "fr-FR-DeniseNeural",
}

# 人口 < 1000 万只给官方语言一条（与前端卡片规则一致，避免小国堆一堆语种）
SMALL_POP = 10_000_000

_VOICES = None


def voices():
    global _VOICES
    if _VOICES is None:
        import edge_tts

        async def go():
            return await edge_tts.list_voices()

        _VOICES = asyncio.run(go())
    return _VOICES


def pick_voice(code):
    """语言代码 -> edge 音色 ShortName（找不到返回 None）。"""
    if not code:
        return None
    if code in VOICE_PIN:
        return VOICE_PIN[code]
    c = code.lower()
    cands = []
    for v in voices():
        loc = (v.get("Locale") or "").lower()
        base = loc.split("-")[0]
        if base == c:
            cands.append(v)
    if not cands:
        return None
    # 同区域优先（fr-FR 优于 fr-CA），其次女声
    def score(v):
        s = 0
        if (v.get("Locale") or "").lower().endswith(("-" + c[:2].upper())):
            s += 2
        if (v.get("Gender") or "").lower() == "female":
            s += 1
        if "Neural" in (v.get("ShortName") or ""):
            s += 1
        return -s
    cands.sort(key=score)
    return cands[0].get("ShortName")


def synth(text, voice, out_path):
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, voice).save(out_path)

    asyncio.run(go())
    return os.path.getsize(out_path)


SPEECH_PROMPT = """你在为一本"国家文化图谱"写语音导览。

国家：{name}（{name_en}）
首都：{capital}

请为下面每一种语言各写**一句 5~6 秒**的口语欢迎语，内容是：欢迎来到这个国家 + 首都是哪里。
要求：
1. 必须是该语言的**日常口语**，不要书面腔、不要翻译腔；
2. 只写一句，不要标题、不要解释；
3. 同时给出这句话的简体中文翻译（供卡片显示）。

语言列表：
{langs}

只输出 JSON，形如：
{{"zh": {{"text": "...", "zh": "..."}}, "en": {{"text": "...", "zh": "..."}}}}
键必须是上面给出的语言代码。"""


def llm_sentences(rec, langs):
    """让大模型写句子。失败返回 {}，由调用方跳过这些语言。"""
    try:
        from llm import chat_json
    except Exception as e:
        print("  ! 无法导入 llm：%s" % e)
        return {}
    listed = "\n".join("- %s（%s）" % (l.get("code"), l.get("name_zh")) for l in langs)
    prompt = SPEECH_PROMPT.format(
        name=rec.get("name_zh") or "", name_en=rec.get("name_en") or "",
        capital=rec.get("capital") or "—", langs=listed)
    try:
        data = chat_json(prompt, scene="speech", max_tokens=900)
    except Exception as e:
        print("  ! 大模型调用失败：%s" % e)
        return {}
    return data if isinstance(data, dict) else {}


def do_country(iso, force=False):
    path = os.path.join(DATA, "%s.json" % iso.lower())
    if not os.path.exists(path):
        print("  ✗ 没有 data/%s.json，先采集" % iso.lower())
        return False
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)

    meta = {}
    try:
        with open(META, encoding="utf-8") as f:
            meta = (json.load(f) or {}).get(iso.upper()) or {}
    except Exception:
        pass
    pop = meta.get("pop") or 0

    all_langs = [l for l in (rec.get("languages") or []) if l.get("role") == "official"]
    if not all_langs:
        all_langs = (rec.get("languages") or [])[:1]
    if pop and pop < SMALL_POP:
        all_langs = all_langs[:1]
    else:
        all_langs = all_langs[:2]
    if not all_langs:
        print("  · 没有语言字段，跳过")
        return True

    need = [l for l in all_langs
            if force or not (l.get("tts_text") and l.get("audio_url"))]
    if need:
        got = llm_sentences(rec, need)
        for l in need:
            g = got.get(l.get("code")) or {}
            if isinstance(g, str):
                g = {"text": g, "zh": ""}
            if g.get("text"):
                l["tts_text"] = g["text"].strip()
                if g.get("zh"):
                    l["tts_text_zh"] = g["zh"].strip()

    ok = 0
    skipped = []
    adir = os.path.join(ROOT, "assets", iso.lower(), "audio")
    os.makedirs(adir, exist_ok=True)
    for l in all_langs:
        text = l.get("tts_text")
        if not text:
            skipped.append("%s（无句子）" % l.get("name_zh"))
            continue
        voice = pick_voice(l.get("code"))
        if not voice:
            skipped.append("%s（无音色）" % l.get("name_zh"))
            continue
        out = os.path.join(adir, "%s.mp3" % l.get("code"))
        if os.path.exists(out) and not force and l.get("audio_url") and l.get("tts_text") == text:
            ok += 1
            continue
        try:
            size = synth(text, voice, out)
        except Exception as e:
            skipped.append("%s（合成失败：%s）" % (l.get("name_zh"), str(e)[:40]))
            continue
        l["audio_url"] = "assets/%s/audio/%s.mp3" % (iso.lower(), l.get("code"))
        l["audio_source"] = "tts_edge"
        l["audio_status"] = "ok"
        l["audio_voice"] = voice
        l["audio_bytes"] = size
        ok += 1
        print("    ✓ %-6s → %-6s %.0f KB  %s"
              % (l.get("name_zh"), l.get("code"), size / 1024, text[:28]))

    if skipped:
        short = rec.get("review_short") or []
        short = [x for x in short if not str(x).startswith("语音")]
        short.append("语音：" + "、".join(skipped))
        rec["review_short"] = short[-3:]
        rec["review_notes"] = (rec.get("review_notes") or []) + ["语音跳过 " + "、".join(skipped)]

    rec["audio_meta"] = rec.get("audio_meta") or {}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("  %s：%d 条音频%s" % (iso, ok, ("，跳过 " + "、".join(skipped)) if skipped else ""))
    return ok > 0 or not need


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("iso", nargs="?", help="ISO 码，如 JP")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="已有音频也重做")
    ap.add_argument("--voices", help="列出某语言可用音色后退出")
    a = ap.parse_args()

    if a.voices:
        code = a.voices.lower()
        for v in voices():
            if (v.get("Locale") or "").lower().startswith(code):
                print("%-28s %-8s %s" % (v.get("ShortName"), v.get("Gender"), v.get("Locale")))
        print("\n自动挑选：%s" % pick_voice(code))
        return 0

    if a.all:
        isos = sorted(x[:-5].upper() for x in os.listdir(DATA)
                      if x.endswith(".json") and not x.startswith("_"))
    elif a.iso:
        isos = [a.iso.upper()]
    else:
        ap.print_help()
        return 1

    ok = 0
    for iso in isos:
        print("\n== %s ==" % iso)
        try:
            ok += bool(do_country(iso, a.force))
        except Exception as e:
            print("  ✗ %s: %s" % (type(e).__name__, e))
    print("\n完成 %d / %d" % (ok, len(isos)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
