#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""寰宇图志 · 本地 TTS（构建期兜底方案，Windows SAPI）

用法：
    python scripts/tts_local.py CN "中国"
    python scripts/tts_local.py CN "粤语" --voice 粤语 --out tailo
    python scripts/tts_local.py --list        # 列出可用音色

为什么不用 Commons 发音：
    Wikidata P443 给的发音文件不保证语种。实测中国的 P443 首个文件是
    Lb-China.ogg —— 卢森堡语读的 "China"，放到演示里明显是错的。
    所以 P443 只在文件名带 zh/chinese/中文 时才采信，否则走本脚本。

输出 16kHz 单声道 WAV，浏览器直接可播。需要 pywin32（本机已装）。
"""

import argparse
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


def list_voices():
    import win32com.client
    sp = win32com.client.Dispatch("SAPI.SpVoice")
    out = []
    for v in sp.GetVoices():
        out.append((v.GetDescription(), v.Id))
    return out


def pick_voice(sp, want_lang):
    """优先挑中文音色；want_lang 里出现 粤/闽 等时仍回退普通话并提示"""
    voices = [(v.GetDescription(), v) for v in sp.GetVoices()]
    prefer = [x for x in voices if "chinese" in x[0].lower() or "中文" in x[0]
              or "zh-cn" in x[0].lower() or "huihui" in x[0].lower()]
    if prefer:
        return prefer[0][1], prefer[0][0]
    return voices[0][1], voices[0][0]


def synth(text, out_path, rate=0, volume=100, voice_hint=None):
    import win32com.client
    sp = win32com.client.Dispatch("SAPI.SpVoice")
    voice, desc = pick_voice(sp, voice_hint)
    sp.Voice = voice
    sp.Rate = rate
    sp.Volume = volume

    fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
    # 22.05kHz 16bit 单声道 —— 语音够用，文件小
    fmt.Type = 22
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Format = fmt
    stream.Open(out_path, 3)  # 3 = SSFMCreateForWrite
    sp.AudioOutputStream = stream
    sp.Speak(text)
    stream.Close()
    return desc, os.path.getsize(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("iso", nargs="?", help="ISO 码，产物写入 assets/{iso}/")
    ap.add_argument("text", nargs="?", help="要合成的文字")
    ap.add_argument("--out", default="pronunciation", help="输出文件名（不含扩展名）")
    ap.add_argument("--voice", help="音色提示，仅用于筛选，如 粤语")
    ap.add_argument("--rate", type=int, default=-1, help="语速 -10~10，默认 -1（略慢）")
    ap.add_argument("--list", action="store_true", help="列出本机音色")
    args = ap.parse_args()

    if args.list:
        for desc, vid in list_voices():
            print("  %-60s %s" % (desc, vid))
        return

    if not args.iso or not args.text:
        ap.error("需要 ISO 码和文本，例如：python scripts/tts_local.py CN \"中国\"")

    iso = args.iso.lower()
    dest_dir = os.path.join(ROOT, "assets", iso)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, args.out + ".wav")

    desc, size = synth(args.text, dest, rate=args.rate, voice_hint=args.voice)
    print("✓ %s" % os.path.relpath(dest, ROOT).replace("\\", "/"))
    print("  音色：%s" % desc)
    print("  文本：%s" % args.text)
    print("  大小：%.1f KB" % (size / 1024))
    if "chinese" not in desc.lower() and "中文" not in desc:
        print("  ! 警告：用到的不是中文音色，效果可能不对")


if __name__ == "__main__":
    main()
