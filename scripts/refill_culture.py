# -*- coding: utf-8 -*-
"""给已采集国家补民俗素材并重写「民俗与日常」。

背景：之前成文只有「维基导语」这一份材料，而导语只讲地理人口政体，
一个民俗细节都没有。模型写民俗只能靠自己的先验 —— 猜对是运气，猜错是编造。

现在多一份「材料三：维基『文化/饮食/节日』章节原文」，模型只做摘编串联，
每个细节都能在来源里找到。这个脚本负责把已有国家的素材补上、正文重写。

用法：
    python scripts/refill_culture.py BR BT DE ...      # 指定国家
    python scripts/refill_culture.py --all             # 已采集的全部（跳过人工稿）
"""
import argparse
import importlib.util
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import netcheck  # noqa: E402

netcheck.setup_once()


def load(name):
    sp = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


C = load("collect")
L = load("llm_tasks")

# 中法美是人工撰写的，不能被覆盖
HAND_WRITTEN = {"CN", "FR", "US"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("isos", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force-excerpts", action="store_true",
                    help="已有素材也重新抓")
    a = ap.parse_args()

    if a.all:
        isos = sorted(os.path.basename(f)[:2].upper()
                      for f in os.listdir(os.path.join(ROOT, "data"))
                      if f.endswith(".json") and not f.startswith("_")
                      and f not in ("index.json", "landmarks.json", "search.json"))
    else:
        isos = [x.upper() for x in a.isos]
    isos = [i for i in isos if i not in HAND_WRITTEN]
    if not isos:
        print("没有要处理的国家")
        return 1

    print("目标 %d 国（中法美是人工稿，已跳过）" % len(isos))
    ok = fail = 0
    for n, iso in enumerate(isos, 1):
        path = os.path.join(ROOT, "data", "%s.json" % iso.lower())
        if not os.path.exists(path):
            print("[%d/%d] %s 无档案，跳过" % (n, len(isos), iso))
            continue
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        name = rec.get("name_zh") or iso

        if a.force_excerpts or not rec.get("culture_excerpts"):
            notes = []
            ex = C.fetch_culture_excerpts(name, notes)
            if ex:
                rec["culture_excerpts"] = ex

        if not rec.get("culture_excerpts"):
            print("[%d/%d] %-3s %-8s 没有民俗素材，正文保持原样" % (n, len(isos), iso, name))
            fail += 1
            continue

        try:
            out = L.compose_history(rec)
        except Exception as e:
            print("[%d/%d] %-3s %-8s 成文失败：%s" % (n, len(isos), iso, name, str(e)[:60]))
            fail += 1
            continue

        rec["history_text"] = out.get("history") or ""
        rec["custom_text"] = out.get("folk") or out["text"]
        rec["custom_text_source"] = {
            "source": out.get("source"),
            "tier": out.get("tier"),
            "chars": {"history": len(rec["history_text"]),
                      "folk": len(rec["custom_text"])},
            "sections": out.get("excerpt_sections") or [],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
            f.write("\n")
        ok += 1
        print("[%d/%d] %-3s %-8s %d 字 · 依据 %s"
              % (n, len(isos), iso, name, out["chars"],
                 "/".join(out.get("excerpt_sections") or []) or "无"))

    print("\n完成：成功 %d，失败 %d" % (ok, fail))
    print("下一步：python scripts/sync_index.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
