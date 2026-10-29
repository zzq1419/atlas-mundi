# -*- coding: utf-8 -*-
"""把旧档案里合并的「历史与民俗」拆成 history_text + custom_text。

背景：2026-10-29 之前，成文是一整段 custom_text，内部靠空行分两段
（prompt 里写死：第一段历史、第二段民俗）。现在数据层直接分两个字段，
前端就能给「历史」「民俗」两个小标题。

这个脚本只做字段重排，不调模型、不改一个字 —— 花 0 元。
需要重新写内容请用 refill_culture.py。

用法：
    python scripts/split_culture.py --dry     # 只看会怎么拆
    python scripts/split_culture.py           # 落盘
"""
import argparse
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {"index.json", "landmarks.json", "search.json"}


def split(text):
    ps = [x.strip() for x in (text or "").split("\n\n") if x.strip()]
    if len(ps) >= 2:
        return ps[0], "\n\n".join(ps[1:])
    return "", (ps[0] if ps else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    done = kept = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "*.json"))):
        base = os.path.basename(path)
        if base.startswith("_") or base in SKIP:
            continue
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        if rec.get("history_text"):
            continue
        src = rec.get("custom_text") or ""
        if not src:
            continue
        hist, folk = split(src)
        if not hist:
            print("  %-3s %-8s 只有一段，拆不开（需重跑成文）"
                  % (rec.get("iso_a2"), rec.get("name_zh")))
            kept += 1
            continue
        print("  %-3s %-8s 历史 %d 字 / 民俗 %d 字"
              % (rec.get("iso_a2"), rec.get("name_zh"), len(hist), len(folk)))
        if not a.dry:
            rec["history_text"] = hist
            rec["custom_text"] = folk
            src_meta = rec.get("custom_text_source") or {}
            src_meta["split_from_merged"] = True
            rec["custom_text_source"] = src_meta
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
                f.write("\n")
        done += 1

    print("\n%s：拆分 %d，未拆 %d" % ("预演" if a.dry else "完成", done, kept))
    return 0


if __name__ == "__main__":
    sys.exit(main())
