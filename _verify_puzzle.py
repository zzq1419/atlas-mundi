# -*- coding: utf-8 -*-
"""验证 2026-10-29 这批改动：
   1. 历史 / 民俗 是否分成两节（有 .sub-label 两个）
   2. 国界轮廓加载是否还把正文往下挤（对比轮廓出现前后 dtext 的 top）
   3. 拼图模式：关面板后金线留不留；关全部国境线是否清盘
   4. 经纬线首次点击是否还有长任务
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

OUT = os.path.join("shots", "puzzle")
URL = "http://127.0.0.1:8787/index.html"
os.makedirs(OUT, exist_ok=True)

report = {}


def open_via_search(page, kw):
    page.click("#q")
    time.sleep(0.3)
    page.fill("#q", kw)
    time.sleep(1.0)
    page.wait_for_selector("#q-res .sr-item", timeout=15000)
    page.click("#q-res .sr-item")
    time.sleep(2.4)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True,
                          args=["--use-angle=d3d11", "--ignore-gpu-blocklist"])
    page = b.new_page(viewport={"width": 1600, "height": 900})
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append("console:" + m.text) if m.type == "error" else None)

    page.goto(URL, wait_until="load")
    page.wait_for_function("window.__sb !== undefined", timeout=60000)
    time.sleep(6)                      # 等预热（1.5s + 0.7s + 建线）

    report["warm"] = page.evaluate("__sb()")

    # ---- 经纬线首点：长任务 ----
    page.evaluate("""() => {
      window.__lt = [];
      try {
        new PerformanceObserver(function (l) {
          l.getEntries().forEach(function (e) { window.__lt.push(Math.round(e.duration)); });
        }).observe({ entryTypes: ['longtask'] });
      } catch (e) {}
    }""")
    page.click("#btn-grid")
    time.sleep(1.2)
    report["gridLongTasks"] = page.evaluate("window.__lt")
    report["gridOn"] = page.evaluate("__sb().gridVisible")
    page.screenshot(path=os.path.join(OUT, "01-grid.png"))

    # ---- 打开德国：分节 + 轮廓抖动 ----
    open_via_search(page, "德国")
    page.wait_for_selector("#detail.open", timeout=20000)
    # 轮廓是 220ms 后画的，先记一次 top，再等它出现后记一次
    page.evaluate("""() => {
      var t = document.querySelector('#d-body .dtext');
      window.__t1 = t ? t.getBoundingClientRect().top : null;
    }""")
    time.sleep(2.2)
    page.evaluate("""() => {
      var t = document.querySelector('#d-body .dtext');
      window.__t2 = t ? t.getBoundingClientRect().top : null;
      window.__labels = Array.prototype.map.call(
        document.querySelectorAll('#d-body .dtext .sub-label'),
        function (n) { return n.textContent; });
      window.__svg = !!document.querySelector('#d-body .geo-svg svg');
    }""")
    report["dtextTopBefore"] = page.evaluate("window.__t1")
    report["dtextTopAfter"] = page.evaluate("window.__t2")
    report["subLabels"] = page.evaluate("window.__labels")
    report["outlineSvg"] = page.evaluate("window.__svg")
    page.screenshot(path=os.path.join(OUT, "02-detail.png"), full_page=False)
    report["afterOpenDE"] = page.evaluate("__sb()")

    # ---- 关面板：金线是否留着 ----
    page.click("#d-close")
    time.sleep(1.6)
    report["afterCloseDE"] = page.evaluate("__sb()")
    page.screenshot(path=os.path.join(OUT, "03-closed-de.png"))

    # ---- 再开日本：两块都亮 ----
    open_via_search(page, "日本")
    page.wait_for_selector("#detail.open", timeout=20000)
    time.sleep(1.2)
    page.click("#d-close")
    time.sleep(1.2)
    report["afterTwo"] = page.evaluate("__sb()")
    page.screenshot(path=os.path.join(OUT, "04-two-lit.png"))

    # ---- 全量国境线：开 → 关（清盘） ----
    page.click("#btn-borders")
    time.sleep(3.0)
    report["allOn"] = page.evaluate("__sb()")
    page.screenshot(path=os.path.join(OUT, "05-all-borders.png"))
    page.click("#btn-borders")
    time.sleep(1.2)
    report["allOff"] = page.evaluate("__sb()")
    page.screenshot(path=os.path.join(OUT, "06-cleared.png"))

    report["errors"] = errs[:10]
    b.close()

print(json.dumps(report, ensure_ascii=False, indent=2))
