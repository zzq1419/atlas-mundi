# -*- coding: utf-8 -*-
"""重取各国官方语言列表（只动 languages 字段，不动其他）。

为什么需要单跑一步：
    采集时的规则是"官方语言只留前 2 个"，瑞士因此只剩德语和意大利语，
    法语、罗曼什语直接消失；印度也只留下印地语和英语各一条。
    规则已经改成按国家规模给 3~4 个，但重跑 `collect.py` 会把图片、
    摘要、语音全部重抓一遍（几十分钟），代价太大。

这个脚本只调一次 Wikidata、只改 languages，已有音频/句子按语言代码继承。

用法：
    python scripts/fix_languages.py --dry      # 只报告会怎么变
    python scripts/fix_languages.py            # 落盘
    python scripts/fix_languages.py --only CH SG
"""
import argparse
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import netcheck  # noqa: E402
netcheck.setup_once()
import collect as C  # noqa: E402

DATA = os.path.join(ROOT, "data")
SKIP = {"index.json", "landmarks.json", "search.json"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    ids = C._load_json(os.path.join(DATA, "_ids.json"), {})
    files = sorted(glob.glob(os.path.join(DATA, "*.json")))
    changed = same = 0
    for path in files:
        base = os.path.basename(path)
        if base.startswith("_") or base in SKIP:
            continue
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        iso = str(rec.get("iso_a2") or "").upper()
        if not iso:
            continue
        if a.only and iso not in {x.upper() for x in a.only}:
            continue
        qid = rec.get("qid") or (ids.get(iso) or {}).get("qid")
        if not qid:
            print("  ! %s 没有 QID，跳过" % iso)
            continue

        old = list(rec.get("languages") or [])   # 复制一份：下面要就地追加
        notes = []
        try:
            wd = C.fetch_wikidata(iso, qid, notes)
        except Exception as e:
            print("  ! %s Wikidata 失败：%s" % (iso, e))
            continue
        new = wd.get("languages") or []
        if not new:
            print("  ! %s 没取到语言" % iso)
            continue

        # 旧条目里的音频/句子/TTS 元数据按语言代码继承，别因为换了列表把声音丢掉
        by_code = {str(x.get("code") or ""): x for x in old}
        for l in new:
            prev = by_code.get(str(l.get("code") or ""))
            if not prev:
                continue
            for k in ("audio_url", "audio_source", "audio_status", "audio_voice",
                      "audio_bytes", "tts_text", "tts_text_zh"):
                if prev.get(k):
                    l[k] = prev[k]

        # 合并而不是覆盖：旧列表里可能有人工补的条目（中国的粤语、美国的英语），
        # Wikidata 那套 P37 不一定有。只追加缺的，绝不删已有的。
        have = {str(x.get("code") or "") for x in old}
        for l in new:
            if str(l.get("code") or "") in have:
                continue
            old.append(l)
            have.add(str(l.get("code") or ""))
        new = old[:4]

        old_names = [x.get("name_zh") for x in (rec.get("languages") or [])]
        new_names = [x.get("name_zh") for x in new]
        # 注意：这里必须用"追加前的快照"比较，否则 old 已被就地改过，
        # 比较永远相等 → 改动被静默丢弃（第一版就踩了这个坑）。
        if old_names == new_names:
            same += 1
            continue
        print("  %-3s %-8s %s → %s" % (iso, rec.get("name_zh"),
                                      "/".join(old_names) or "—", "/".join(new_names)))
        if a.dry:
            continue
        rec["languages"] = new
        # 旧备注里"保留 N 个"的说法已经不成立，删掉免得误导
        rec["review_notes"] = [n for n in (rec.get("review_notes") or [])
                               if not str(n).startswith("P37 返回")]
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
            f.write("\n")
        changed += 1

    print("\n%s：变动 %d，未变 %d" % ("预演" if a.dry else "完成", changed, same))
    return 0


if __name__ == "__main__":
    sys.exit(main())
