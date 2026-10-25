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
    "br": "fr-FR-DeniseNeural",      # 布列塔尼语无独立音色，先用法语顶上并标注
    "en": "en-US-AriaNeural",
    "es": "es-ES-ElviraNeural",
    "ar": "ar-SA-ZariyahNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "de": "de-DE-KatjaNeural",
    "pt": "pt-BR-FranciscaNeural",
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
    done, failed = [], []

    for l in langs:
        code = l.get("code") or "zh"
        text = l.get("tts_text")
        if not text:
            print("  - %-6s 无 tts_text，跳过" % code)
            continue
        voice = VOICE.get(code, "en-US-AriaNeural")
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
                print("  ✗ %-6s SAPI 也失败：%s" % (code, e))
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
        print("  ✓ %-6s %-22s %6.1f KB  [%s]  %s" % (code, rel, size / 1024, use_engine, text[:24]))

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

    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("\n已写回 data/%s.json，共 %d 条语音" % (slug, len(done)))


if __name__ == "__main__":
    main()
