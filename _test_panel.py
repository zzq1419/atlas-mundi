# -*- coding: utf-8 -*-
"""面板回归测试：换图 + 外语翻译 + 地标首图是否加载。"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8787/index.html"


def open_country(page, name, iso):
    page.click("#q")
    page.fill("#q", name)
    time.sleep(0.8)
    rows = page.query_selector_all(".sr-item, .sr-country-row")
    assert rows, "搜索「%s」没有任何结果" % name
    rows[0].click()
    time.sleep(3.0)


def probe(page):
    return page.evaluate("""() => {
      const w = document.querySelector('.dimg-wrap');
      const img = document.querySelector('.dimg');
      const thumbs = [...document.querySelectorAll('.ts-item')];
      return {
        wrapClass: w ? w.className : null,
        src: img ? img.getAttribute('src') : null,
        nat: img ? img.naturalWidth : 0,
        thumbs: thumbs.length,
        zh: [...document.querySelectorAll('.lt-zh')].length,
        srcLines: [...document.querySelectorAll('.lt-src')].length,
        captions: [...document.querySelectorAll('.cap')].map(n => n.textContent).slice(0, 3),
      };
    }""")


def main():
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True,
                              args=["--enable-unsafe-swiftshader", "--use-gl=angle",
                                    "--use-angle=swiftshader"])
        pg = b.new_page(viewport={"width": 1600, "height": 900})
        errs = []
        pg.on("console", lambda m: errs.append("CONSOLE %s: %s" % (m.type, m.text))
              if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append("PAGEERROR: %s" % e))
        pg.goto(URL, wait_until="load")
        time.sleep(4)

        for name, iso in [("埃及", "EG"), ("日本", "JP")]:
            open_country(pg, name, iso)
            first = probe(pg)
            pg.screenshot(path="shots/panel_%s_1.png" % iso)
            # 点第二张缩略图
            thumbs = pg.query_selector_all(".ts-item")
            if len(thumbs) > 1:
                thumbs[1].click()
                time.sleep(2.5)
            second = probe(pg)
            pg.screenshot(path="shots/panel_%s_2.png" % iso)
            # 再点第三张
            thumbs = pg.query_selector_all(".ts-item")
            if len(thumbs) > 2:
                thumbs[2].click()
                time.sleep(2.5)
            third = probe(pg)
            pg.screenshot(path="shots/panel_%s_3.png" % iso)
            out.append({"iso": iso, "first": first, "second": second, "third": third})
            # 关面板
            pg.click("#d-close")
            time.sleep(1.2)

        b.close()

    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("ERRORS:", json.dumps(errs, ensure_ascii=False))

    ok = True
    for r in out:
        for k in ("first", "second", "third"):
            s = r[k]
            if not s["nat"]:
                print("[FAIL] %s %s 主图没加载（src=%s, wrap=%s）" % (r["iso"], k, s["src"], s["wrapClass"]))
                ok = False
        if r["first"]["zh"] < 1:
            print("[FAIL] %s 没有中文翻译" % r["iso"])
            ok = False
    print("RESULT:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    sys.exit(main())
