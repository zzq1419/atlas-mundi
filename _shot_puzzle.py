# -*- coding: utf-8 -*-
"""拼图模式成品截图：点三个国家 → 关面板 → 回到欧亚上空看三块金线。"""
import json
import os
import time

from playwright.sync_api import sync_playwright

OUT = os.path.join("shots", "puzzle")
os.makedirs(OUT, exist_ok=True)
report = {}


def open_country(page, kw):
    page.click("#q")
    time.sleep(0.25)
    page.fill("#q", kw)
    time.sleep(0.9)
    page.wait_for_selector("#q-res .sr-item", timeout=15000)
    page.click("#q-res .sr-item")
    page.wait_for_selector("#detail.open", timeout=20000)
    time.sleep(2.0)
    page.click("#d-close")
    time.sleep(1.0)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True,
                          args=["--use-angle=d3d11", "--ignore-gpu-blocklist"])
    page = b.new_page(viewport={"width": 1600, "height": 900})
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto("http://127.0.0.1:8787/index.html", wait_until="load")
    page.wait_for_function("window.__sb !== undefined", timeout=60000)
    time.sleep(7)

    # 首图加载耗时：从点开起到 picWrap 变 loaded
    page.click("#q")
    time.sleep(0.25)
    page.fill("#q", "德国")
    time.sleep(0.9)
    page.evaluate("window.__t0 = performance.now()")
    page.click("#q-res .sr-item")
    page.wait_for_selector("#detail .dimg-wrap.loaded", timeout=20000)
    report["firstImageMs"] = round(page.evaluate("performance.now() - window.__t0"))
    page.screenshot(path=os.path.join(OUT, "20-panel-top.png"))
    page.click("#d-close")
    time.sleep(1.0)

    for kw in ("中国", "日本"):
        open_country(page, kw)

    report["lit"] = page.evaluate("__sb()")

    page.click("#btn-china")
    time.sleep(2.0)
    page.mouse.move(760, 450)
    page.mouse.wheel(0, 700)
    time.sleep(2.2)
    page.screenshot(path=os.path.join(OUT, "21-puzzle-3.png"))
    page.mouse.wheel(0, 500)
    time.sleep(2.0)
    page.screenshot(path=os.path.join(OUT, "22-puzzle-3-wide.png"))

    report["errors"] = errs[:8]
    b.close()

print(json.dumps(report, ensure_ascii=False, indent=1))
