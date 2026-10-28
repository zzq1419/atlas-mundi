#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""寰宇图志 · 构建期 TTS（多语言，两种引擎）

用法：
    python scripts/tts.py CN                # 按 data/cn.json 里的 tts_text 生成全部语言音频
    python scripts/tts.py CN --engine sapi  # 强制离线（仅普通话）
    python scripts/tts.py --voices          # 列出常用音色

引擎：
    edge  —— 微软 Edge 朗读接口，免费无 key，支持粤语/法语/英语等，输出 24kHz MP3
    sapi  —— Windows 本地 SAPI，完全离线，但本机只有普通话音色（Huihui）

为什么不用 Wikidata 的 P443 发音：
    P443 只保证「这个实体有发音文件」，不保证语种。中国 Q148 的首个发音是
    Lb-China.ogg —— 卢森堡语读的 China。所以 P443 只在文件名带
    zh-/chinese/中文 时才采信，区域语言（粤语）一律走 TTS。

语音内容约定：
    每个语言一条 5~6 秒的句子，不是干念国名。念两三个字播放条一闪就没，
    演示时看不出"这是语音模态"，等于白做一条模态。
"""

import argparse
import asyncio
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


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    enc = (sys.stdout.encoding or "").lower()
    if enc not in ("utf-8", "utf8", "cp936", "gbk", "gb2312", "cp65001"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 语言码 -> edge 音色。扩量时补这里。
VOICE = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "cmn": "zh-CN-XiaoxiaoNeural",
    "yue": "zh-HK-HiuMaanNeural",
    "fr": "fr-FR-DeniseNeural",
    "en": "en-US-AriaNeural",
    "es": "es-ES-ElviraNeural",
    "ar": "ar-SA-ZariyahNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "de": "de-DE-KatjaNeural",
    "pt": "pt-BR-FranciscaNeural",
}

# 没有可用合成音色的语种：明确跳过并在 review_notes 留痕，不要用邻近语种硬读
NO_VOICE = {
    "br": "布列塔尼语无可用合成音色（Edge TTS 不含凯尔特语支）",
    "oc": "奥克语无可用合成音色",
    "haw": "夏威夷语无可用合成音色",
}

# 手写句库：每国每条语言一句 5~6 秒的话。比模板拼装自然得多，也方便你改。
PHRASES = {
    ("CN", "zh"): "你好，欢迎来到中国。首都是北京，万里长城横贯北方。",
    ("CN", "yue"): "你好，歡迎嚟到中國。首都係北京，萬里長城橫貫北方。",
    ("FR", "fr"): "Bonjour, bienvenue en France. Sa capitale est Paris, et la tour Eiffel se dresse au bord de la Seine.",
    ("US", "en"): "Hello, welcome to the United States. Its capital is Washington, D.C., and the Grand Canyon lies in the southwest.",
}

# 句库里没有时的兜底模板
TEMPLATE = {
    "zh": "你好，欢迎来到{name}。首都是{cap}。",
    "en": "Hello, welcome to {name}. Its capital is {cap}.",
    "fr": "Bonjour, bienvenue en {name}. Sa capitale est {cap}.",
}

VOICE_NAMES = {
    "zh-CN-XiaoxiaoNeural": "晓晓 · 普通话（女）",
    "zh-CN-YunxiNeural": "云希 · 普通话（男）",
    "zh-HK-HiuMaanNeural": "曉曼 · 粤语（女）",
    "zh-TW-HsiaoChenNeural": "曉臻 · 台湾国语（女）",
    "fr-FR-DeniseNeural": "Denise · 法语（女）",
    "en-US-AriaNeural": "Aria · 英语（女）",
}


def synth_edge(text, voice, out_path):
    import edge_tts

    async def run():
        c = edge_tts.Communicate(text, voice)
        await c.save(out_path)

    asyncio.run(run())
    return os.path.getsize(out_path)


def synth_sapi(text, out_path):
    """离线兜底。SAPI 只能写 WAV，本机只有普通话音色。"""
    import win32com.client
    sp = win32com.client.Dispatch("SAPI.SpVoice")
    zh = [v for v in sp.GetVoices()
          if "chinese" in v.GetDescription().lower() or "中文" in v.GetDescription()]
    if not zh:
        raise RuntimeError("本机没有中文音色")
    sp.Voice = zh[0]
    sp.Rate = -1
    fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
    fmt.Type = 22
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Format = fmt
    stream.Open(out_path, 3)
    sp.AudioOutputStream = stream
    sp.Speak(text)
    stream.Close()
    return os.path.getsize(out_path), zh[0].GetDescription()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("iso", nargs="?", help="ISO 码，按 data/{iso}.json 生成")
    ap.add_argument("--engine", choices=["auto", "edge", "sapi"], default="auto")
    ap.add_argument("--voices", action="store_true", help="列出常用音色")
    args = ap.parse_args()

    if args.voices:
        for k, v in VOICE_NAMES.items():
            print("  %-24s %s" % (k, v))
        return
    if not args.iso:
        ap.error("需要 ISO 码，例如：python scripts/tts.py CN")

    iso = args.iso.upper()
    slug = iso.lower()
    path = os.path.join(ROOT, "data", "%s.json" % slug)
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)

    langs = rec.get("languages") or []
    if not langs:
        print("!! data/%s.json 里没有 languages，先跑 collect.py" % slug)
        return

    out_dir = os.path.join(ROOT, "assets", slug, "audio")
    os.makedirs(out_dir, exist_ok=True)
    engine = args.engine
    done, failed, skipped = [], [], []

    for l in langs:
        code = l.get("code") or "zh"
        if code in NO_VOICE:
            print("  - %-6s 跳过：%s" % (code, NO_VOICE[code]))
            skipped.append(code)
            continue
        text = (l.get("tts_text")
                or PHRASES.get((iso, code))
                or TEMPLATE.get(code, "").format(name=rec.get("name_local") or rec.get("name_zh") or "",
                                                 cap=rec.get("capital") or ""))
        if not text or text.strip() in ("你好，欢迎来到。首都是。", "Hello, welcome to . Its capital is ."):
            print("  - %-6s 没有可用文案，跳过" % code)
            skipped.append(code)
            continue
        l["tts_text"] = text
        voice = VOICE.get(code)
        if not voice:
            # 关键：查不到音色就跳过。以前默认回落到英语音色，
            # 等于用英语读夏威夷语，是错的。
            print("  - %-6s 跳过：无 %s 的合成音色" % (code, code))
            skipped.append(code)
            continue
        ext, use_engine = ".mp3", engine

        if use_engine in ("auto", "edge"):
            dest = os.path.join(out_dir, code + ".mp3")
            try:
                size = synth_edge(text, voice, dest)
                if size < 4000:
                    raise RuntimeError("产物过小（%d 字节）" % size)
                use_engine = "edge"
            except Exception as e:
                print("  ! edge 失败（%s），回落 SAPI" % str(e)[:70])
                use_engine = "sapi" if engine == "auto" else "fail"

        if use_engine == "sapi":
            ext = ".wav"
            dest = os.path.join(out_dir, code + ".wav")
            try:
                size, desc = synth_sapi(text, dest)
                voice = desc
            except Exception as e:
                print("  [x] %-6s SAPI 也失败：%s" % (code, e))
                failed.append(code)
                continue
        elif use_engine == "fail":
            failed.append(code)
            continue

        rel = "assets/%s/audio/%s%s" % (slug, code, ext)
        l["audio_url"] = rel
        l["audio_source"] = "tts_" + use_engine
        l["audio_voice"] = voice
        l["audio_bytes"] = size
        l["audio_status"] = "ok"
        done.append((code, rel, size, use_engine))
        print("  [ok] %-6s %-22s %6.1f KB  [%s]  %s" % (code, rel, size / 1024, use_engine, text[:24]))

    if not done:
        print("!! 没有任何语音生成成功")
        return

    # 顶层 audio_url 用第一条成功的（通常是官方语言）
    rec["audio_url"] = done[0][1]
    rec["audio_source"] = done[0][3]
    rec["audio_meta"] = {
        "engine": done[0][3],
        "voice": next((l.get("audio_voice") for l in langs if l.get("audio_url") == done[0][1]), ""),
        "text": next((l.get("tts_text") for l in langs if l.get("audio_url") == done[0][1]), ""),
        "per_language": [{"code": c, "url": u, "bytes": s} for c, u, s, _ in done],
        "note": "顶层音频为官方语言；区域语言见 languages[].audio_url",
    }
    if failed:
        rec.setdefault("review_notes", []).append("以下语言 TTS 失败：%s" % "、".join(failed))
    if skipped:
        rec["review_notes"] = [n for n in rec.get("review_notes", []) if "无音色" not in n]
        rec.setdefault("review_notes", []).append(
            "以下语言未生成语音（无合适音色，不用邻近语种硬读）：%s" % "、".join(skipped))

    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("\n已写回 data/%s.json，共 %d 条语音" % (slug, len(done)))


if __name__ == "__main__":
    main()
