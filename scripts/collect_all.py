#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""全量采集编排器：一条命令把 200+ 国家按阶段跑完。

为什么要一个编排器
------------------
`collect.py / llm_tasks.py / tts.py / optimize_images.py` 都只处理"一个国家"，
手工循环 200 次必然出错：中途断了不知道跑到哪、某个国家挂了整批停、
代理抖动没人重试、也不知道还差哪些。这个脚本只负责"调度 + 记录 + 断点续跑"，
采集逻辑一行都不复制。

阶段（可单独跑，也可 --all 串起来）
-----------------------------------
    ids      把 ISO 解析成 Wikidata QID（scripts/resolve_ids.py）
    collect  Wikidata + 维基摘要 + Commons 图片 + 国界（scripts/collect.py）
    llm      特征抽取 / 摘要精炼 / 图注翻译 / 质检 / 问答（需要 DEEPSEEK_API_KEY）
    speech   多语种语音：先让大模型写句子，再用 Edge TTS 合成（scripts/speech_all.py）
    images   原图压缩成 WebP + 缩略图（scripts/optimize_images.py）
    index    同步 index.json + 重建检索索引
    upload   上传 OBS

典型用法
--------
    python scripts/collect_all.py --stage ids
    python scripts/collect_all.py --stage collect --limit 5      # 先试 5 个
    python scripts/collect_all.py --stage collect --all          # 全部（可反复跑）
    python scripts/collect_all.py --stage llm --limit 20
    python scripts/collect_all.py --all                          # 全流程

断点续跑
--------
每个国家完成后写一行 logs/collect_all.jsonl；`collect` 阶段默认跳过"已有摘要且有图"
的国家，`--force` 才会重采。中途 Ctrl+C 不会丢进度。

失败不中断
----------
单个国家异常只记入报告，继续下一个；最后打印失败清单和对应命令，
照着单跑即可（例如 `python scripts/collect.py XK`）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
from datetime import datetime

try:
    enc = (sys.stdout.encoding or "").lower()
    if enc not in ("utf-8", "utf8", "cp936", "gbk", "gb2312", "cp65001"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

# 让 .env 里的 key 对子进程可见（子进程继承 os.environ）
try:
    from envfile import load as _load_env
except ImportError:
    try:
        from scripts.envfile import load as _load_env
    except ImportError:
        _load_env = None
if _load_env:
    _load_env()
PY = sys.executable or "python"
META = os.path.join(ROOT, "geo", "meta.json")
IDS = os.path.join(ROOT, "data", "_ids.json")
LOGDIR = os.path.join(ROOT, "logs")
JSONL = os.path.join(LOGDIR, "collect_all.jsonl")
REPORT = os.path.join(ROOT, "data", "_collect_report.json")


def log(msg=""):
    print(msg, flush=True)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def run(cmd, timeout=1200, idle=300):
    """跑一个子进程：输出逐行实时写日志并回显，带"无输出看门狗"。

    为什么不用 subprocess.run —— 它是等子进程结束后一次性把输出返回的。
    中途卡在哪个请求上完全看不出来，用户看到的就是"窗口不动了，也不知道在干嘛"。
    实测卡在某一国的图片下载上，13 分钟零输出，只能靠猜。
    改成逐行读之后，卡住时日志的最后一行就是卡住的位置。

    看门狗：连续 idle 秒没有新输出就杀掉、记失败、继续下一个国家。
    一个国家的网络抖动不该拖住整批 200 多个。
    """
    import queue
    import threading

    name = "_".join(os.path.basename(c).replace(".py", "") for c in cmd[:2])
    os.makedirs(LOGDIR, exist_ok=True)
    path = os.path.join(LOGDIR, "run_%s.log" % name.replace(" ", "_"))
    env = dict(os.environ)
    # 强制子进程用 UTF-8 输出：否则它按 cp936 输出、这里按 UTF-8 解码，
    # logs/*.log 会变成一片"锟斤拷"，出事时完全没法查
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    def emit(text):
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except UnicodeEncodeError:
            # 控制台是 cp936，遇到生僻字/带音标的语言名会炸
            sys.stdout.write(text.encode("gbk", "replace").decode("gbk"))
            sys.stdout.flush()

    with open(path, "a", encoding="utf-8") as f:
        f.write("\n$ %s\n" % " ".join(cmd))
        f.flush()
        try:
            p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, bufsize=0)
        except Exception as e:
            f.write("!! 启动失败：%s\n" % e)
            return 1, str(e)

        q = queue.Queue()

        def pump():
            for line in iter(p.stdout.readline, b""):
                q.put(line)
            q.put(None)

        threading.Thread(target=pump, daemon=True).start()

        buf, t0, last, killed = [], time.time(), time.time(), ""
        while True:
            try:
                line = q.get(timeout=1.0)
            except queue.Empty:
                now = time.time()
                if now - last > idle:
                    killed = "连续 %d 秒没有输出" % idle
                elif now - t0 > timeout:
                    killed = "整国超过 %d 秒" % timeout
                if killed:
                    try:
                        p.kill()
                    except Exception:
                        pass
                    break
                continue
            if line is None:
                break
            last = time.time()
            text = line.decode("utf-8", "replace")
            buf.append(text)
            f.write(text)
            f.flush()
            emit(text)

        if killed:
            msg = ("\n!! %s，已强制跳过这一国（%.1f 分钟）\n"
                   % (killed, (time.time() - t0) / 60))
            f.write(msg)
            emit(msg)
            try:
                p.wait(timeout=10)
            except Exception:
                pass
            return 124, "".join(buf) + msg

        p.wait()
        return p.returncode, "".join(buf)


def note(iso, stage, ok, detail=""):
    os.makedirs(LOGDIR, exist_ok=True)
    rec = {"ts": datetime.now().isoformat(timespec="seconds"),
           "iso": iso, "stage": stage, "ok": ok, "detail": detail[:400]}
    with open(JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def record_has(iso, need=("summary_text",)):
    rec = read_json(os.path.join(ROOT, "data", "%s.json" % iso.lower()), {})
    if not rec:
        return False
    for k in need:
        if not rec.get(k):
            return False
    return True


def target_isos(a):
    meta = read_json(META, {})
    if not meta:
        log("缺 geo/meta.json：先跑 python scripts/build_countries.py")
        raise SystemExit(1)
    isos = sorted(meta.keys())
    if a.only:
        want = {x.upper() for x in a.only}
        isos = [i for i in isos if i.upper() in want]
    if a.min_pop:
        isos = [i for i in isos if (meta.get(i) or {}).get("pop", 0) >= a.min_pop]
    if a.limit:
        isos = isos[:a.limit]
    return isos


def stage_ids(a, isos):
    cmd = [PY, os.path.join(SCRIPTS, "resolve_ids.py")]
    if a.proxy:
        cmd += ["--proxy", a.proxy]
    if a.limit:
        cmd += ["--limit", str(a.limit)]
    if a.only:
        cmd += ["--only"] + list(a.only)
    code, out = run(cmd, timeout=3600)
    log(out[-1500:] if out else "")
    return code == 0


def stage_collect(a, isos):
    have_ids = read_json(IDS, {})
    if not have_ids:
        log("!! data/_ids.json 不存在：先跑 --stage ids")
        return False
    todo = []
    for iso in isos:
        if not (have_ids.get(iso) or {}).get("qid"):
            note(iso, "collect", False, "无 QID")
            continue
        if not a.force and record_has(iso, ("summary_text", "landmark_images")):
            continue
        todo.append(iso)

    log("待采集 %d 个（跳过已完成 %d 个）" % (len(todo), len(isos) - len(todo)))
    ok = fail = 0
    fails = []
    for n, iso in enumerate(todo, 1):
        name = (read_json(META, {}).get(iso) or {}).get("n", iso)
        log("\n[%d/%d] %s %s" % (n, len(todo), iso, name))
        cmd = [PY, os.path.join(SCRIPTS, "collect.py"), iso]
        if a.geo:
            cmd.append("--geo")
        code, out = run(cmd, timeout=a.country_timeout, idle=a.idle_kill)
        good = code == 0 and record_has(iso, ("summary_text",))
        note(iso, "collect", good, out[-300:] if not good else "")
        if good:
            ok += 1
            # 采集成功后立刻压图，避免 assets 里堆一堆 3MB 的 jpg
            if a.optimize_inline:
                run([PY, os.path.join(SCRIPTS, "optimize_images.py"), iso], timeout=600)
        else:
            fail += 1
            fails.append(iso)
            log("  [x] 失败：%s" % out.strip().splitlines()[-1][:120] if out else "  [x] 失败")
        if a.sleep:
            time.sleep(a.sleep)
    log("\n采集完成：成功 %d，失败 %d" % (ok, fail))
    if fails:
        log("失败清单：%s" % " ".join(fails))
        log("单独重试：python scripts/collect.py <ISO> --geo")
    return fail == 0


def stage_llm(a, isos):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        log("!! 没有 DEEPSEEK_API_KEY，跳过 llm 阶段（export DEEPSEEK_API_KEY=sk-...）")
        return False
    todo = [i for i in isos if record_has(i)]
    log("LLM 阶段 %d 个（每个国家约 6~9 次调用）" % len(todo))
    ok = fail = 0
    for n, iso in enumerate(todo, 1):
        if not a.force:
            rec = read_json(os.path.join(ROOT, "data", "%s.json" % iso.lower()), {})
            # 两段都要在：只有 custom_text 的是旧版合并稿，还得补 history_text
            if rec.get("custom_facets") and rec.get("custom_text") and rec.get("history_text"):
                continue
        log("[%d/%d] %s" % (n, len(todo), iso))
        cmd = [PY, os.path.join(SCRIPTS, "llm_tasks.py"), "--run", iso,
               "--only", a.llm_only, "--apply"]
        code, out = run(cmd, timeout=a.country_timeout, idle=a.idle_kill)
        good = code == 0
        note(iso, "llm", good, "" if good else out[-300:])
        ok += good
        fail += (not good)
    log("LLM 完成：成功 %d，失败 %d" % (ok, fail))
    return fail == 0


def stage_speech(a, isos):
    path = os.path.join(SCRIPTS, "speech_all.py")
    if not os.path.exists(path):
        log("!! 缺 scripts/speech_all.py")
        return False
    todo = [i for i in isos if record_has(i)]
    log("语音阶段 %d 个" % len(todo))
    ok = fail = 0
    for n, iso in enumerate(todo, 1):
        code, out = run([PY, path, iso], timeout=a.country_timeout, idle=a.idle_kill)
        good = code == 0
        note(iso, "speech", good, "" if good else out[-300:])
        ok += good
        fail += (not good)
        if n % 10 == 0:
            log("  … %d/%d" % (n, len(todo)))
    log("语音完成：成功 %d，失败 %d" % (ok, fail))
    return fail == 0


def stage_images(a, isos):
    # --prune：WebP 写好就删源 jpg。223 国不删的话源图就有 400MB+
    code, out = run([PY, os.path.join(SCRIPTS, "optimize_images.py"), "--all", "--prune"],
                    timeout=7200)
    log(out[-800:] if out else "")
    return code == 0


def stage_index(a, isos):
    ok = True
    for script in ("sync_index.py", "build_search_index.py"):
        code, out = run([PY, os.path.join(SCRIPTS, script)], timeout=1800)
        log("  %s → %s" % (script, "ok" if code == 0 else "fail"))
        if code != 0:
            log(out[-600:] if out else "")
            ok = False
    return ok


def stage_upload(a, isos):
    if not (os.environ.get("HUAWEI_AK") and os.environ.get("HUAWEI_SK")):
        log("!! 缺 HUAWEI_AK / HUAWEI_SK，跳过上传")
        return False
    code, out = run([PY, os.path.join(SCRIPTS, "upload_obs.py"),
                     "--bucket", a.bucket, "--region", a.region], timeout=7200)
    log(out[-600:] if out else "")
    return code == 0


STAGES = ["ids", "collect", "llm", "speech", "images", "index", "upload"]


def main():
    ap = argparse.ArgumentParser(description="全量国家采集编排器")
    ap.add_argument("--stage", action="append", choices=STAGES,
                    help="要跑的阶段，可重复；不给则按 --all")
    ap.add_argument("--all", action="store_true", help="按顺序跑全部阶段")
    ap.add_argument("--only", nargs="*", help="只处理这些 ISO")
    ap.add_argument("--limit", type=int, default=0, help="最多处理多少个国家（先试水）")
    ap.add_argument("--min-pop", type=int, default=0, help="只处理人口 >= N 的国家")
    ap.add_argument("--force", action="store_true", help="已完成也重做")
    ap.add_argument("--geo", action="store_true", help="采集时顺便抓国界（默认不要，已有 geo/c*.json）")
    ap.add_argument("--sleep", type=float, default=1.0, help="国家之间的间隔秒数")
    ap.add_argument("--country-timeout", type=int, default=1200)
    ap.add_argument("--no-optimize-inline", dest="optimize_inline", action="store_false",
                    help="采集后不立刻压图（最后统一跑 images 阶段）")
    ap.add_argument("--proxy", help="如 http://127.0.0.1:7890（也会读 HTTPS_PROXY）")
    ap.add_argument("--llm-only", default="all",
                    help="传给 llm_tasks.py 的 --only（all / facets / summary / "
                         "compose / captions / audit / qa，一次只能一类）")
    ap.add_argument("--bucket", default="atlas-mundi-1419")
    ap.add_argument("--region", default="cn-east-3")
    ap.add_argument("--plan", action="store_true", help="只统计规模，不执行")
    a = ap.parse_args()

    # 代理要"探测一次 + 设进环境变量"，子进程继承：
    # urllib 不读 Windows 系统代理，只认这几条环境变量。
    try:
        import netcheck
        netcheck.setup(a.proxy, verbose=True)
    except ImportError:
        if a.proxy:
            for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                os.environ[k] = a.proxy

    isos = target_isos(a)

    if a.plan:
        ids = read_json(IDS, {})
        ready = sum(1 for i in isos if record_has(i, ("summary_text", "landmark_images")))
        with_llm = sum(1 for i in isos if record_has(i) and
                       read_json(os.path.join(ROOT, "data", "%s.json" % i.lower()), {})
                       .get("custom_facets"))
        log("目标国家 %d 个" % len(isos))
        log("  已有 QID   %d" % sum(1 for i in isos if (ids.get(i) or {}).get("qid")))
        log("  已采完     %d" % ready)
        log("  已过 LLM   %d" % with_llm)
        log("  待采集     %d" % (len(isos) - ready))
        return 0

    stages = ["ids", "collect", "llm", "speech", "images", "index", "upload"] if a.all \
        else (a.stage or ["collect"])

    log("阶段：%s   国家：%d" % (" → ".join(stages), len(isos)))
    t0 = time.time()
    results = {}
    for st in stages:
        log("\n===== %s =====" % st)
        fn = {"ids": stage_ids, "collect": stage_collect, "llm": stage_llm,
              "speech": stage_speech, "images": stage_images, "index": stage_index,
              "upload": stage_upload}[st]
        try:
            results[st] = fn(a, isos)
        except KeyboardInterrupt:
            log("\n已中断。已完成的部分都在盘上，重跑同一命令即可接着做。")
            return 130
        except Exception as e:
            results[st] = False
            log("!! %s 阶段异常：%s: %s" % (st, type(e).__name__, e))

    log("\n===== 汇总（%.1f 分钟）=====" % ((time.time() - t0) / 60))
    for st in stages:
        log("  %-8s %s" % (st, "[ok]" if results.get(st) else "[x]"))

    rep = {"at": datetime.now().isoformat(timespec="seconds"),
           "isos": len(isos), "stages": {k: bool(v) for k, v in results.items()}}
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
        f.write("\n")
    log("报告：data/_collect_report.json")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
