#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给每个国家生成「地标清单」，写进 data/landmarks.json，供 fill_images.py 搜图。

为什么需要这一步
----------------
`collect.py` 只取 Wikidata 的 P18（代表图），每国就一张，而且经常是定位地图、
国旗或卫星云图 —— 实测日本拿到的是"2003 年 5 月日本卫星影像"，美国拿到的是
UNOCHA 的定位地图。三国那套好看的地标图（长城、太和殿、兵马俑、布达拉宫）
是人工往 `data/landmarks.json` 里写检索词换来的。

223 个国家不可能一个个手写，但也不能靠关键词瞎猜。所以：**让模型出候选，
用 Commons 的真实检索结果做裁判** —— `fill_images.py` 会按 kw 搜 File 命名空间、
要求文件名含 must、滤掉地图/旗帜/徽章、要求宽度 >= 800，拿不到就跳过。
模型编出来的地标（例如某个不存在的宫殿）会自然被淘汰。

产物与人工版同构：

    data/landmarks.json
    {"countries": {"JP": [{"zh": "富士山", "en": "Mount Fuji", ...}, ...]}}

用法
----
    python scripts/build_landmarks.py --only JP          # 先看一个
    python scripts/build_landmarks.py --limit 5          # 试 5 个
    python scripts/build_landmarks.py                    # 全量（约 10~20 分钟）
    python scripts/build_landmarks.py --force --only JP  # 重做已有的

之后：
    python scripts/fill_images.py --all
    python scripts/optimize_images.py --all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

try:
    from envfile import load as load_env
except ImportError:
    from scripts.envfile import load as load_env

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm                                                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "geo", "meta.json")
CONF = os.path.join(ROOT, "data", "landmarks.json")

SYSTEM = (
    "你是旅行百科编辑。只列真实存在、在 Wikimedia Commons 上几乎一定能找到照片的地方，"
    "宁缺毋滥：不确定的不要写。"
)

PROMPT = """国家/地区：{name}（{en}，{iso}）

请列出 6 个最能代表这个国家的地标，按"外国人最可能想看"排序。

挑选规则：
1. 优先著名的古迹、自然奇观、城市天际线标志、宗教建筑；
2. **不要**选：博物馆/大学/医院/公司总部/体育场这类到处都有的通用建筑，
   不要选国旗、国徽、地图、领导人；
3. 小国如果凑不出 6 个真正的名胜，就给 2~4 个，宁可少不要凑数。

每一项给三个字段：
- zh：中文名，4~10 字，直接当图注（例如"富士山""吴哥窟"）
- kw：英文检索词，2~5 个词，要具体到这一处地标（例如 "Mount Fuji Kawaguchiko"）
- must：小写英文关键词，用于过滤搜错的图，必须出现在文件名里（例如 "fuji"）

只输出 JSON：
{{"items": [{{"zh": "富士山", "kw": "Mount Fuji Kawaguchiko", "must": "fuji"}}]}}"""


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def clean(items):
    """校验模型输出：字段齐、长度合理、must 是英文小写、去重。"""
    out, seen = [], set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        zh = str(it.get("zh") or "").strip()
        kw = str(it.get("kw") or "").strip()
        must = str(it.get("must") or "").strip().lower()
        if not (2 <= len(zh) <= 14) or not kw:
            continue
        # kw 必须是英文：中文检索词在 Commons 的 File 命名空间里几乎搜不到
        if not all(ord(c) < 128 for c in kw):
            continue
        if not must:
            must = kw.split()[-1].lower()
        if not all(ord(c) < 128 for c in must) or len(must) < 3:
            continue
        if must in seen:
            continue
        seen.add(must)
        out.append({"zh": zh, "en": kw, "queries": [zh], "kw": kw, "must": must})
    return out[:6]


def one(iso, meta, n):
    name = meta.get("n") or iso
    en = meta.get("en") or ""
    d = llm.chat_json(PROMPT.format(name=name, en=en, iso=iso),
                      scene="landmarks", max_tokens=700, system=SYSTEM)
    items = d.get("items") if isinstance(d, dict) else None
    return clean(items)


def main():
    ap = argparse.ArgumentParser(description="生成各国地标清单（写 data/landmarks.json）")
    ap.add_argument("--only", nargs="*", help="只处理这些 ISO")
    ap.add_argument("--limit", type=int, default=0, help="最多处理多少个（按人口降序取）")
    ap.add_argument("--min-pop", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="已有配置也重做")
    ap.add_argument("--n", type=int, default=6, help="每题要几处（默认 6）")
    a = ap.parse_args()

    load_env()
    if not (os.environ.get("DEEPSEEK_API_KEY") or "").strip():
        print("[STOP] 没有 DEEPSEEK_API_KEY：检查仓库根的 .env")
        return 1

    meta = read_json(META, {})
    conf = read_json(CONF, {"countries": {}})
    conf.setdefault("countries", {})
    countries = conf["countries"]

    isos = [i for i in meta if i.upper() not in ("", None)]
    if a.only:
        want = {x.upper() for x in a.only}
        isos = [i for i in isos if i.upper() in want]
    if a.min_pop:
        isos = [i for i in isos if (meta.get(i) or {}).get("pop", 0) >= a.min_pop]
    if a.limit:
        isos = sorted(isos, key=lambda i: -((meta.get(i) or {}).get("pop", 0)))[:a.limit]

    todo = [i for i in isos if a.force or not countries.get(i)]
    print("目标 %d 个，待生成 %d 个（已有 %d 个跳过）"
          % (len(isos), len(todo), len(isos) - len(todo)))
    if not todo:
        print("都已生成。要重做加 --force")
        return 0

    ok = fail = 0
    t0 = time.time()
    for n, iso in enumerate(todo, 1):
        m = meta.get(iso) or {}
        try:
            items = one(iso, m, a.n)
        except Exception as e:
            print("[%d/%d] %-3s %-8s 失败：%s" % (n, len(todo), iso, m.get("n", ""), e))
            fail += 1
            continue
        if not items:
            print("[%d/%d] %-3s %-8s 无可用地标（模型给的都过不了校验）"
                  % (n, len(todo), iso, m.get("n", "")))
            fail += 1
            continue
        countries[iso] = items
        ok += 1
        print("[%d/%d] %-3s %-8s %s"
              % (n, len(todo), iso, m.get("n", ""), "、".join(x["zh"] for x in items)))
        if n % 10 == 0:
            write(CONF, conf)

    write(CONF, conf)
    print("\n完成：成功 %d，失败 %d，用时 %.1f 分钟 → %s"
          % (ok, fail, (time.time() - t0) / 60, CONF))
    if fail:
        print("失败的重跑一次即可（已成功的会跳过）：python scripts/build_landmarks.py")
    print("\n下一步：python scripts/fill_images.py --all")
    return 0


def write(path, conf):
    """写回时保持原有字段（note / schema）不动，只更新 countries。"""
    conf.setdefault("note", "各国地标清单：fill_images.py 按 kw 在 Commons 搜图，must 用于过滤误配")
    conf.setdefault("schema", 1)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(conf, f, ensure_ascii=False, indent=1)
        f.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
