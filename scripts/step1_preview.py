#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第一步：体检 → ISO 解析 → 试采 5 国 → 生成审核页。

为什么拆成"两步"
----------------
全量是 223 个国家、好几个小时。如果一开始就 --all，等三小时后才发现
"图片全挑成了市政厅"或者"某些国家的语言代码是 Qxxxx"，返工代价太大。
所以先走这一步：把 QID 全部解析完（这步错了后面全错），再挑 5 个
在地理、语种、数据量上都不一样的国家试采，出一个人眼可看的审核页。

四个动作
--------
0 体检    Python / edge-tts / Pillow / geo/meta.json / 四个域名连通 / DeepSeek key
1 解析    scripts/resolve_ids.py：ISO → Wikidata QID（223 个，约 10 分钟）
2 试采    scripts/collect_all.py --stage collect --only <5 个 ISO>
3 审核    review/试采审核.html + 控制台质量表（摘要字数/图片数/图注/语言/坐标）

跑完看审核页，确认没问题再双击「2_全量采集.bat」。

用法
----
    python scripts/step1_preview.py                # 默认 5 国：JP EG BR NO KE
    python scripts/step1_preview.py --check        # 只体检，不动网络请求
    python scripts/step1_preview.py --only JP KE   # 自己指定试采国
    python scripts/step1_preview.py --proxy http://127.0.0.1:7890
    python scripts/step1_preview.py --skip-ids     # QID 已解析好，只试采
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    from envfile import load as load_env, mask as mask_key
except ImportError:                                   # python scripts/xxx.py 直接跑时
    from scripts.envfile import load as load_env, mask as mask_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
PY = sys.executable or "python"
META = os.path.join(ROOT, "geo", "meta.json")
IDS = os.path.join(ROOT, "data", "_ids.json")
REVIEW_DIR = os.path.join(ROOT, "review")

# 试采的 5 个国：故意选得不一样，好把各种坑一次暴露出来
#   JP 岛国、语种单一、维基条目极长
#   EG 非洲 + 阿拉伯语（RTL 语音、非拉丁文字）
#   BR 南美、葡萄牙语、国土大、图片多
#   NO 北欧、人口少、语言有书面/口头两套
#   KE 非洲、英语+斯瓦希里语双语、维基条目偏短
DEFAULT_PICK = ["JP", "EG", "BR", "NO", "KE"]

HOSTS = [
    ("Wikidata 实体/搜索", "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q17&props=labels&format=json"),
    ("中文维基百科", "https://zh.wikipedia.org/w/api.php?action=query&format=json&titles=%E6%97%A5%E6%9C%AC"),
    ("Commons 图片", "https://commons.wikimedia.org/w/api.php?action=query&format=json&titles=File:Example.jpg"),
]


def hr(title=""):
    if title:
        print("\n" + "=" * 62)
        print(title)
        print("=" * 62)
    else:
        print("-" * 62)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def http_ok(url, timeout=10, headers=None):
    """只用来看"通不通"：返回 (ok, 说明)。200~399 算通。"""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, "HTTP %d" % r.status
    except urllib.error.HTTPError as e:
        return (400 <= e.code < 500), "HTTP %d" % e.code
    except Exception as e:
        return False, "%s" % type(e).__name__


# --------------------------------------------------------------- 0 体检
def step_health(a) -> bool:
    hr("0 · 环境体检")
    ok_all = True

    print("  Python      %s" % sys.version.split()[0])
    if sys.version_info < (3, 9):
        print("  [FAIL] 需要 3.9 以上")
        ok_all = False

    for mod, pkg in (("edge_tts", "edge-tts"), ("PIL", "Pillow")):
        try:
            m = __import__(mod)
            print("  %-11s %s" % (pkg, getattr(m, "__version__", "已安装")))
        except ImportError:
            print("  [FAIL] 缺 %s —— 运行：%s -m pip install %s" % (pkg, PY, pkg))
            ok_all = False

    if not os.path.exists(META):
        print("  [FAIL] 缺 geo/meta.json —— 先跑 python scripts/build_countries.py")
        ok_all = False
    else:
        meta = read_json(META, {})
        print("  geo/meta    %d 个国家/地区" % len(meta))

    ids = read_json(IDS, {})
    have = sum(1 for k, v in ids.items() if not k.startswith("_") and (v or {}).get("qid"))
    print("  data/_ids  %s" % ("已解析 %d 个" % have if have else "尚未生成（下一步会做）"))

    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        print("  [FAIL] 没有 DEEPSEEK_API_KEY：检查仓库根目录的 .env")
        ok_all = False
    else:
        good, why = http_ok("https://api.deepseek.com/models", timeout=15,
                            headers={"Authorization": "Bearer " + key})
        if good:
            print("  DeepSeek    key %s 可用（模型 %s）"
                  % (mask_key(key), os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")))
        else:
            print("  [FAIL] DeepSeek 不可用（%s）—— 检查代理或 key" % why)
            ok_all = False

    print("\n  网络连通（代理开了就必须通；返回 4xx 也算通，说明域名可达）：")
    for name, url in HOSTS:
        good, why = http_ok(url, timeout=12)
        print("    %-4s %-18s %s" % ("[ok]" if good else "[--]", name, why))
        if not good:
            ok_all = False

    if not ok_all:
        print("""
  提示：如果浏览器能打开维基但这里不通，说明代理没被 Python 继承。
  显式指定一次即可（Clash 默认 7890，v2rayN 默认 10809）：
      python scripts/step1_preview.py --proxy http://127.0.0.1:7890
""")
    return ok_all


# --------------------------------------------------------------- 1 解析 QID
def step_ids(a) -> bool:
    hr("1 · ISO → Wikidata QID")
    cmd = [PY, os.path.join(SCRIPTS, "resolve_ids.py")]
    if a.limit:
        cmd += ["--limit", str(a.limit)]
    if a.proxy:
        cmd += ["--proxy", a.proxy]
    t0 = time.time()
    print("  $ %s\n" % " ".join(cmd[1:]))
    code = subprocess.call(cmd, cwd=ROOT)
    print("\n  用时 %.1f 分钟" % ((time.time() - t0) / 60))

    ids = read_json(IDS, {})
    total = sum(1 for k in ids if not k.startswith("_"))
    have = sum(1 for k, v in ids.items() if not k.startswith("_") and (v or {}).get("qid"))
    print("  解析结果：%d / %d" % (have, len(read_json(META, {}))))
    bad = read_json(os.path.join(ROOT, "data", "_ids_unresolved.json"), {})
    if bad:
        print("  未解析 %d 个：%s" % (len(bad), " ".join(list(bad)[:20])))
        print("  手工补：python scripts/resolve_ids.py --set XK=Q1246")
    return code == 0 and have > 0


# --------------------------------------------------------------- 2 试采
def step_collect(a, isos) -> bool:
    hr("2 · 试采 %d 国：%s" % (len(isos), " ".join(isos)))
    cmd = [PY, os.path.join(SCRIPTS, "collect_all.py"), "--stage", "collect",
           "--only"] + isos
    if a.proxy:
        cmd += ["--proxy", a.proxy]
    t0 = time.time()
    code = subprocess.call(cmd, cwd=ROOT)
    print("\n  用时 %.1f 分钟" % ((time.time() - t0) / 60))
    return code == 0


# --------------------------------------------------------------- 3 审核
def inspect(iso):
    """读出采集结果，算一版质量指标 + 问题清单。"""
    rec = read_json(os.path.join(ROOT, "data", "%s.json" % iso.lower()), {})
    meta = read_json(META, {}).get(iso, {})
    imgs = rec.get("landmark_images") or []
    langs = rec.get("languages") or []
    summ = rec.get("summary_text") or ""
    problems = []

    if not rec:
        return {"iso": iso, "name": meta.get("n", iso), "rec": {}, "imgs": [], "langs": [],
                "chars": 0,
                "problems": ["没有 data/%s.json（采集失败）" % iso.lower()]}

    if len(summ) < 160:
        problems.append("摘要只有 %d 字" % len(summ))
    if len(imgs) < 3:
        problems.append("只有 %d 张图" % len(imgs))
    no_cap = [x for x in imgs if not (x.get("caption_zh") or "").strip()]
    if no_cap:
        problems.append("%d 张图缺图注" % len(no_cap))
    if not langs:
        problems.append("没有识别到语言")
    elif not any(l.get("role") == "official" for l in langs):
        problems.append("没有官方语言标记")
    # 图片是否真的下载到本地（只下了 remote_url 的话 assets 里是空的）
    missing = [x for x in imgs
               if x.get("url") and not os.path.exists(os.path.join(ROOT, x["url"]))]
    if missing:
        problems.append("%d 张图没落到本地" % len(missing))
    cen = rec.get("centroid") or []
    if len(cen) != 2:
        problems.append("缺坐标")
    srcs = [str(x.get("source") or "") for x in (rec.get("sources") or [])]
    if not any("wikipedia" in s_ for s_ in srcs):
        problems.append("缺维基来源")
    if not rec.get("qid"):
        problems.append("缺 QID")

    return {"iso": iso, "name": rec.get("name_zh") or meta.get("n", iso), "rec": rec,
            "imgs": imgs, "langs": langs, "chars": len(summ), "problems": problems}


PAGE_HEAD = """<!doctype html><meta charset="utf-8">
<title>试采审核 · 寰宇图志</title>
<style>
  :root{color-scheme:dark}
  body{margin:0;padding:28px 32px 60px;background:#070b12;color:#dbe4f2;
       font:15px/1.7 "PingFang SC","Microsoft YaHei",system-ui,sans-serif}
  h1{font-size:22px;margin:0 0 6px;letter-spacing:.04em}
  .sub{color:#7f93ad;font-size:13px;margin-bottom:22px;max-width:76ch}
  .card{border:1px solid rgba(126,158,198,.20);border-radius:14px;margin-bottom:20px;
        background:rgba(12,18,30,.9);overflow:hidden}
  .card.bad{border-color:rgba(226,132,120,.45)}
  .card header{padding:14px 18px;border-bottom:1px solid rgba(126,158,198,.14);
               display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap}
  .card h2{margin:0;font-size:19px}
  .card h2 small{color:#7f93ad;font-size:12px;letter-spacing:.1em;margin-left:6px}
  .kpi span{font-size:12px;color:#9fb3cb;margin-left:14px}
  .body{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:18px;padding:16px 18px}
  @media (max-width:900px){.body{grid-template-columns:1fr}}
  .pics{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-content:start}
  figure{margin:0}
  figure img{width:100%;height:132px;object-fit:cover;border-radius:8px;
             background:#0d1420;border:1px solid rgba(126,158,198,.16)}
  figcaption{font-size:12px;color:#9fb3cb;margin-top:4px}
  h3{font-size:13px;color:#8fb4de;margin:14px 0 6px;font-weight:600;letter-spacing:.05em}
  h3:first-child{margin-top:0}
  p{margin:0;font-size:14px;color:#c8d4e6}
  ul{margin:0;padding-left:18px;font-size:13px}
  .langs li{margin-bottom:2px}
  .langs i{color:#7f93ad;font-style:normal;font-size:11px;margin-left:4px}
  .probs li{color:#f0b4a8}
  .probs li.pass{color:#8ed6a8}
  .none{color:#7f93ad}
  .meta{font-size:12px;color:#7f93ad;margin-top:10px}
</style>
<h1>试采审核 · __N__ 国</h1>
<div class="sub">看四件事：图片是不是该国的地标、图注对不对、摘要够不够、语言识别对不对。
有问题的卡片边框是红的。确认没问题后双击「2_第二步_全量采集.bat」。</div>
"""

CARD = """
<section class="card __FLAG__">
  <header>
    <h2>__NAME__ <small>__ISO__</small></h2>
    <div class="kpi"><span>摘要 __CH__ 字</span><span>图片 __IM__ 张</span><span>语言 __LG__ 种</span></div>
  </header>
  <div class="body">
    <div class="pics">__PICS__</div>
    <div class="text">
      <h3>摘要</h3>
      <p>__SUM__</p>
      <h3>语言</h3>
      <ul class="langs">__LANGS__</ul>
      <h3>检查</h3>
      <ul class="probs">__PROBS__</ul>
      <div class="meta">__META__</div>
    </div>
  </div>
</section>"""


def build_review(rows, path):
    """生成一个人眼可看的静态审核页：图片、图注、摘要、语言、问题。

    注意：这里**不能用 % 格式化整页** —— CSS 里全是 `100%`、`width:50%`，
    一遇到 `%` 就会抛 "unsupported format character"。改用占位符替换。
    """
    es = html.escape
    out = []
    for r in rows:
        rec = r["rec"]
        pics = []
        for im in r["imgs"][:6]:
            src = im.get("thumb_url") or im.get("url") or ""
            if src and not src.startswith("http"):
                src = "../" + src
            pics.append('<figure><img src="%s" alt="" loading="lazy">'
                        '<figcaption>%s</figcaption></figure>'
                        % (es(src), es(im.get("caption_zh") or "（无图注）")))
        def lang_line(l):
            # 只显示中文名 + 代码 + 角色。name_local 常常就是中文名本身
            # （"现代标准汉语""粤语"），再打一遍纯属噪音，审核时看代码更准。
            return '<li><b>%s</b> <i>%s · %s</i></li>' % (
                es(l.get("name_zh") or l.get("code") or "?"),
                es(l.get("code") or "?"), es(l.get("role") or "-"))

        langs = "".join(lang_line(l) for l in r["langs"]) or '<li class="none">（无）</li>'
        probs = ("".join("<li>%s</li>" % es(p) for p in r["problems"])
                 if r["problems"] else '<li class="pass">无异常</li>')
        cen = rec.get("centroid") or []
        meta_line = "QID %s · 首都 %s · 大洲 %s · 坐标 %s" % (
            rec.get("qid") or "—", rec.get("capital") or "—",
            rec.get("continent") or "—",
            ("%.2f, %.2f" % (cen[1], cen[0])) if len(cen) == 2 else "—")

        html_card = CARD
        for k, v in (("__FLAG__", "ok" if not r["problems"] else "bad"),
                     ("__NAME__", es(r["name"])), ("__ISO__", es(r["iso"])),
                     ("__CH__", str(r["chars"])), ("__IM__", str(len(r["imgs"]))),
                     ("__LG__", str(len(r["langs"]))),
                     ("__PICS__", "".join(pics) or "<p class='none'>（没有图片）</p>"),
                     ("__SUM__", es((rec.get("summary_text") or "")[:900])),
                     ("__LANGS__", langs), ("__PROBS__", probs),
                     ("__META__", es(meta_line))):
            html_card = html_card.replace(k, v)
        out.append(html_card)

    doc = PAGE_HEAD.replace("__N__", str(len(rows))) + "".join(out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)
    return path


def step_review(rows):
    hr("3 · 质量表")
    print("  %-4s %-8s %6s %5s %4s  %s" % ("ISO", "国家", "摘要", "图片", "语言", "问题"))
    bad = 0
    for r in rows:
        print("  %-4s %-8s %5d字 %4d张 %3d种  %s"
              % (r["iso"], r["name"][:8], r["chars"], len(r["imgs"]), len(r["langs"]),
                 "；".join(r["problems"]) if r["problems"] else "—"))
        bad += bool(r["problems"])

    path = build_review(rows, os.path.join(REVIEW_DIR, "试采审核.html"))
    print("\n  审核页：%s" % path)
    try:
        if os.name == "nt":
            os.startfile(path)                       # 直接用默认浏览器打开
        else:
            subprocess.call(["open" if sys.platform == "darwin" else "xdg-open", path])
    except Exception:
        print("  （没能自动打开，手动双击上面这个文件）")
    return bad


def main():
    ap = argparse.ArgumentParser(description="第一步：体检 + QID 解析 + 试采 5 国")
    ap.add_argument("--only", nargs="*", default=None, help="自定义试采国，如 --only JP KE")
    ap.add_argument("--limit", type=int, default=0, help="QID 解析只做前 N 个（试水）")
    ap.add_argument("--skip-ids", action="store_true", help="跳过 QID 解析（已解析过）")
    ap.add_argument("--skip-collect", action="store_true", help="只体检 + 解析，不试采")
    ap.add_argument("--check", action="store_true", help="只体检，不发起采集")
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or None,
                    help="如 http://127.0.0.1:7890（也会读 HTTPS_PROXY）")
    a = ap.parse_args()

    load_env()
    if a.proxy:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[k] = a.proxy

    print("寰宇图志 · 全量采集 第一步")
    print("仓库：%s" % ROOT)
    if a.proxy:
        print("代理：%s" % a.proxy)

    healthy = step_health(a)
    if a.check:
        print("\n（--check：到此为止）")
        return 0 if healthy else 1
    if not healthy:
        print("\n[STOP] 体检没过，先解决上面 [FAIL] / [--] 的项再重跑。")
        return 1

    if not a.skip_ids:
        if not step_ids(a):
            print("\n[STOP] QID 解析失败，后面无法继续。")
            return 1
    else:
        ids = read_json(IDS, {})
        if not ids:
            print("\n[STOP] --skip-ids 但 data/_ids.json 不存在。")
            return 1

    isos = [x.upper() for x in (a.only or DEFAULT_PICK)]
    if not a.skip_collect:
        if not step_collect(a, isos):
            print("\n[WARN] 试采没全过，看上面的失败清单；审核页照样会生成。")

    rows = [inspect(i) for i in isos]
    step_review(rows)

    print("""
下一步
------
1. 在浏览器里看「试采审核」，重点看：图片是不是该国的地标、图注是否对得上、
   摘要是否通顺、语言有没有识别错（比如把英语当官方语言）。
2. 满意了 → 双击 2_全量采集.bat（全量采集 → 大模型 → 语音 → 压图 → 索引，
   约 4~7 小时，随时 Ctrl+C，重跑接着做）。
3. 有国家质量差 → 单独重跑：python scripts/collect.py JP
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
