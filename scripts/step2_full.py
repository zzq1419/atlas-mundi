#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第二步：一键跑完 3 全量采集 → 4 大模型 → 5 语音 → 6 压图/索引。

定位
----
第一步（step1_preview.py）已经把 QID 解析好、试采了 5 国给人看。
这一步是"确认质量之后的长跑"：223 个国家，4~7 小时，中途可以关掉重跑。

为什么不是简单 `collect_all.py --all`
-------------------------------------
`--all` 会把 ids 和 upload 也带上：ids 已经跑过（重复解析等于白等十分钟），
upload 需要 OBS 密钥且现在不该自动往线上推。所以这里只跑 4 个阶段，
并且每阶段结束打印"这一阶段用了多久 / 失败几个"，而不是最后一次性汇总 ——
跑三小时回来只看一行"[x]"是很难受的。

断点续跑
--------
采集跳过"已有摘要且有图"，大模型跳过"已有 facets 且有 custom_text"，
语音跳过"已有音频"。所以 Ctrl+C 之后重跑同一条命令就是接着做。

用法
----
    python scripts/step2_full.py                 # 全量（采集 → 大模型 → 语音 → 压图/索引）
    python scripts/step2_full.py --limit 10      # 先拿 10 个验证流水线
    python scripts/step2_full.py --from llm      # 采集已跑完，从大模型接着来
    python scripts/step2_full.py --to speech     # 只跑到语音
    python scripts/step2_full.py --skip-collect  # 采集已完整，跳过
    python scripts/step2_full.py --upload        # 额外上传 OBS（需要 HUAWEI_AK/SK）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

# 控制台可能是 cp936：个别符号打不出来时用 ? 替换，别让整段崩掉
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

try:
    from envfile import load as load_env, mask as mask_key
except ImportError:
    from scripts.envfile import load as load_env, mask as mask_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import collect_all as ca                                   # noqa: E402  复用已跑通的阶段函数

META = os.path.join(ROOT, "geo", "meta.json")
IDS = os.path.join(ROOT, "data", "_ids.json")
LOGDIR = os.path.join(ROOT, "logs")

STAGES = ["collect", "landmarks", "verify", "llm", "speech", "images", "index", "upload"]
LABEL = {"collect": "3 · 全量采集（Wikidata + 维基 + 图片）",
         "landmarks": "3b · 地标图（模型候选 + Commons 实搜）",
         "verify": "3c · 视觉复核（大模型看图，收错图 + 补不足）",
         "llm": "4 · 大模型（特征 / 摘要 / 民俗成文 / 图注 / 质检）",
         "speech": "5 · 多语种语音（Edge TTS）",
         "images": "6a · 压图（WebP + 缩略图）",
         "index": "6b · 索引（index.json + 检索）",
         "upload": "7 · 上传 OBS（可选）"}
# 粗略耗时（分钟/国），只用来在开始时给个预期
COST = {"collect": 0.35, "landmarks": 0.55, "verify": 0.75, "llm": 0.45,
        "speech": 0.10, "images": 0.03, "index": 0.0, "upload": 0.0}
# 视觉复核对钱有硬闸门：花到这个数就停（默认 6 元，可 --verify-budget 改）
# 每张图约 0.0008 元，6 元能验 7000 多张 —— 覆盖 220 国 × 5 张还有余量。
VERIFY_BUDGET = 6.0


def hr(title=""):
    print("\n" + "=" * 62)
    print(title)
    print("=" * 62)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def ns(**kw):
    """collect_all 的阶段函数吃的是一个 argparse.Namespace。"""
    d = dict(only=None, min_pop=0, limit=0, force=False, geo=False,
             country_timeout=900, idle_kill=300, sleep=0.8, optimize_inline=True,
             proxy=None, llm_only="all", bucket="atlas-mundi-1419",
             region="cn-east-3")
    d.update(kw)
    return argparse.Namespace(**d)


def preflight(isos, stages):
    """开跑前把"必然失败"的情况拦掉，别让人等三小时才发现 key 是空的。"""
    ok = True
    ids = read_json(IDS, {})
    no_qid = [i for i in isos if not (ids.get(i) or {}).get("qid")]
    ready = sum(1 for i in isos if ca.record_has(i, ("summary_text", "landmark_images")))

    print("  目标国家      %d 个" % len(isos))
    print("  已有 QID      %d 个" % (len(isos) - len(no_qid)))
    print("  已采集        %d 个" % ready)
    if no_qid:
        print("  [WARN] %d 个没有 QID，采集阶段会跳过：%s"
              % (len(no_qid), " ".join(no_qid[:16])))
        print("         补：python scripts/resolve_ids.py --set XK=Q1246")

    if "llm" in stages:
        key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        if not key:
            print("  [FAIL] 缺 DEEPSEEK_API_KEY（检查 .env），大模型阶段会整段跳过")
            ok = False
        else:
            print("  DeepSeek      key %s · 模型 %s"
                  % (mask_key(key), os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")))
    if "upload" in stages and not (os.environ.get("HUAWEI_AK") and os.environ.get("HUAWEI_SK")):
        print("  [FAIL] 缺 HUAWEI_AK / HUAWEI_SK，上传阶段会跳过")
        ok = False

    mins = sum(COST.get(s, 0) for s in stages) * len(isos)
    print("\n  预计耗时      %s（按每国 1 次采集 + 6 次大模型调用粗估）"
          % ("不到 1 分钟" if mins < 1 else "%d~%d 分钟" % (mins * 0.8, mins * 1.6)))
    print("  中断随时可    Ctrl+C 后重跑同一命令就是接着做")
    return ok


def stage_landmarks(a, isos):
    """地标图：模型写候选 → Commons 实搜 → 写回带中文图注的 landmark_images。

    为什么不是 collect 的一部分：collect 只能拿 Wikidata 的 P18（每国一张，
    经常是卫星影像/定位地图）。能看的地标图要靠"点名 + 搜索 + 过滤"，
    两件事的失败原因完全不同，合成一步会没法定位问题。
    """
    have = [i for i in isos if os.path.exists(
        os.path.join(ROOT, "data", "%s.json" % i.lower()))]
    if not have:
        print("  没有已采集的国家，跳过")
        return False

    print("  ① 生成地标清单（已有的跳过）")
    code1, out1 = ca.run([ca.PY, os.path.join(SCRIPTS, "build_landmarks.py"),
                          "--only"] + have, timeout=7200)
    print(" " * 2 + "\n  ".join((out1 or "").strip().splitlines()[-4:]))

    # ② 只给"还没有中文图注"的国家抓图（避免每次重跑都重新下载几百张）
    todo = []
    for i in have:
        rec = read_json(os.path.join(ROOT, "data", "%s.json" % i.lower()), {})
        imgs = rec.get("landmark_images") or []
        if not imgs or not any((x.get("caption_zh") or "").strip() for x in imgs):
            todo.append(i)
    print("  ② 抓图 %d 个（已有中文图注的 %d 个跳过）" % (len(todo), len(have) - len(todo)))
    if not todo:
        return code1 == 0
    code2 = fail = 0
    for n, i in enumerate(todo, 1):
        code, out = ca.run([ca.PY, os.path.join(SCRIPTS, "fill_images.py"), i], timeout=900)
        ok = code == 0 and "已写回" in (out or "")
        if not ok:
            fail += 1
        ca.note(i, "landmarks", ok, "" if ok else (out or "")[-300:])
        if n % 10 == 0:
            print("    … %d/%d（失败 %d）" % (n, len(todo), fail))
    print("  抓图完成：%d 个成功，%d 个没拿到" % (len(todo) - fail, fail))
    return fail == 0 or fail < len(todo) // 2


def stage_verify(a, isos):
    """让多模态模型看图，收掉"合规但不对"的图，并把数量不足的补齐。

    为什么单独一段而不塞进 landmarks：两者的失败模式完全不同 ——
    fill_images 是"搜到没有 / 尺寸对不对"，这里是"画面对不对"。
    合起来出错时没法判断是哪一步的问题。

    钱有硬闸门：--budget 花完就停，中断后重跑靠 data/_vision_cache.json 接着来，
    验过的图不会再花钱。
    """
    have = [i for i in isos if os.path.exists(
        os.path.join(ROOT, "data", "%s.json" % i.lower()))]
    if not have:
        print("  没有已采集的国家，跳过")
        return False
    print("  预算 %.1f 元、最多补 3 轮；验过的图有缓存，重跑不重复花钱" % VERIFY_BUDGET)
    code, out = ca.run([ca.PY, os.path.join(SCRIPTS, "verify_images.py"),
                        "--only"] + have +
                       ["--budget", str(VERIFY_BUDGET), "--max-rounds", "3"],
                      timeout=14400)
    tail = [l for l in (out or "").splitlines() if l.strip()][-6:]
    print("\n".join("  " + l for l in tail))
    # 预算花完不算法失败 —— 剩下没验的下次接着来
    return code == 0 or "预算" in (out or "")


def report(isos, path):
    """跑完出一个人看的汇总：哪些国家缺哪一块。"""
    rows = []
    for iso in isos:
        rec = read_json(os.path.join(ROOT, "data", "%s.json" % iso.lower()), {})
        if not rec:
            rows.append((iso, "—", 0, 0, 0, "无档案"))
            continue
        imgs = rec.get("landmark_images") or []
        langs = rec.get("languages") or []
        audio = sum(1 for l in langs if l.get("audio_url"))
        facets = 1 if rec.get("custom_facets") else 0
        # 成文分「历史」「民俗」两段存放，统计要合并；旧档案只有 custom_text
        text = len(rec.get("history_text") or "") + len(rec.get("custom_text") or "")
        miss = []
        if len(rec.get("summary_text") or "") < 160:
            miss.append("摘要短")
        if len(imgs) < 3:
            miss.append("图少")
        elif not any((x.get("caption_zh") or "").strip() for x in imgs):
            miss.append("图无中文注")
        if not facets:
            miss.append("无特征")
        if text < 180:
            miss.append("无成文")
        if not audio:
            miss.append("无语音")
        rows.append((iso, rec.get("name_zh") or iso, len(rec.get("summary_text") or ""),
                     len(imgs), audio, "、".join(miss) or "完整"))

    full = sum(1 for r in rows if r[5] == "完整")
    lines = ["# 全量采集报告", "",
             "生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
             "",
             "口径：「完整」= 摘要 ≥160 字 + 图片 ≥3 张 + 有文化特征 + 有民俗成文 + 有语音。",
             "只跑了部分阶段时，未跑到的字段会自然显示为缺口。",
             "", "| 国家 | ISO | 摘要 | 图片 | 语音 | 缺口 |", "| --- | --- | --- | --- | --- | --- |"]
    for r in sorted(rows, key=lambda x: (x[5] == "完整", x[0])):
        lines.append("| %s | %s | %d 字 | %d | %d | %s |" % (r[1], r[0], r[2], r[3], r[4], r[5]))
    lines += ["", "完整 %d / %d（%.0f%%）" % (full, len(rows), 100.0 * full / max(1, len(rows)))]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("  完整 %d / %d（%.0f%%）→ %s"
          % (full, len(rows), 100.0 * full / max(1, len(rows)), path))
    gap = [r for r in rows if r[5] != "完整"]
    if gap:
        print("  还有缺口 %d 个：%s" % (len(gap), " ".join(r[0] for r in gap[:24])))
    return full, len(rows)


def main():
    ap = argparse.ArgumentParser(description="第二步：一键跑完全量采集流水线")
    ap.add_argument("--from", dest="start", default="collect", choices=STAGES,
                    help="从哪个阶段开始（默认 collect）")
    ap.add_argument("--to", dest="end", default="index", choices=STAGES,
                    help="跑到哪个阶段为止（默认 index）")
    ap.add_argument("--only", nargs="*", help="只处理这些 ISO")
    ap.add_argument("--limit", type=int, default=0, help="只做前 N 个（验证流水线用）")
    ap.add_argument("--min-pop", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="已完成也重做")
    ap.add_argument("--skip-collect", action="store_true", help="跳过采集阶段")
    ap.add_argument("--upload", action="store_true", help="最后加一步上传 OBS")
    ap.add_argument("--verify-budget", type=float, default=6.0,
                    help="视觉复核最多花多少钱（元，默认 6；0=不限）")
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or None)
    ap.add_argument("--country-timeout", type=int, default=900,
                    help="单个国家最长跑多久（秒），超了记失败继续下一个")
    ap.add_argument("--idle-kill", type=int, default=300,
                    help="连续多少秒没有输出就认为卡死、跳过（默认 300）")
    a = ap.parse_args()

    global VERIFY_BUDGET
    VERIFY_BUDGET = a.verify_budget

    load_env()
    try:
        from netcheck import setup as net_setup
        proxy, proxy_src = net_setup(a.proxy, verbose=True)
    except ImportError:
        proxy = a.proxy
        if a.proxy:
            for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                os.environ[k] = a.proxy
    a.proxy = proxy

    meta = read_json(META, {})
    if not meta:
        print("[STOP] 缺 geo/meta.json：先跑 python scripts/build_countries.py")
        return 1

    isos = sorted(meta.keys())
    if a.only:
        want = {x.upper() for x in a.only}
        isos = [i for i in isos if i.upper() in want]
    if a.min_pop:
        isos = [i for i in isos if (meta.get(i) or {}).get("pop", 0) >= a.min_pop]
    if a.limit:
        # 试跑要挑"大而全"的国家：按人口降序取前 N，而不是按 ISO 字母序
        # （字母序前三个是安道尔、阿联酋、阿富汗，跑完看不出流水线好不好）
        isos = sorted(isos, key=lambda i: -((meta.get(i) or {}).get("pop", 0)))[:a.limit]

    i0, i1 = STAGES.index(a.start), STAGES.index(a.end)
    stages = STAGES[i0:i1 + 1]
    if a.skip_collect and "collect" in stages:
        stages.remove("collect")
    if a.upload and "upload" not in stages:
        stages.append("upload")

    hr("寰宇图志 · 全量采集 第二步")
    print("  阶段：%s" % " → ".join(stages))
    if not preflight(isos, stages):
        print("\n[STOP] 上面的 [FAIL] 先解决。")
        return 1

    args = ns(only=a.only, limit=a.limit, min_pop=a.min_pop, force=a.force,
              proxy=a.proxy, country_timeout=a.country_timeout,
              idle_kill=a.idle_kill)
    fns = {"collect": ca.stage_collect, "landmarks": stage_landmarks,
           "verify": stage_verify,
           "llm": ca.stage_llm,
           "speech": ca.stage_speech, "images": ca.stage_images,
           "index": ca.stage_index, "upload": ca.stage_upload}

    t_all = time.time()
    results = {}
    for st in stages:
        hr(LABEL.get(st, st))
        t0 = time.time()
        try:
            results[st] = bool(fns[st](args, isos))
        except KeyboardInterrupt:
            print("\n已中断（阶段 %s）。已完成的部分都在盘上，重跑同一命令接着做。" % st)
            return 130
        except Exception as e:
            results[st] = False
            print("!! %s 阶段异常：%s: %s" % (st, type(e).__name__, e))
        print("\n  %s：%s，用时 %.1f 分钟"
              % (st, "通过" if results[st] else "有失败项", (time.time() - t0) / 60))

    hr("汇总（总用时 %.1f 小时）" % ((time.time() - t_all) / 3600))
    for st in stages:
        print("  %-8s %s" % (st, "OK" if results.get(st) else "有失败项（不影响其余国家）"))

    rep = os.path.join(LOGDIR, "采集报告.md")
    print()
    report(isos, rep)

    print("""
接下来
------
* 报告看 logs/采集报告.md，缺口国家按下面方式单独补：
      python scripts/collect.py <ISO>            # 重采
      python scripts/llm_tasks.py --run <ISO> --only all --apply
      python scripts/speech_all.py <ISO>
* 质量抽查：data/_llm/ 里是模型稿（成文/特征/图注），核完再考虑是否信任。
* 发布：跑完告诉我。223 国的 assets 约 60~90MB（压图已删源 jpg），
  现在能走 git（配好代理）一次推完，不用再逐个文件走 API。
""")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
