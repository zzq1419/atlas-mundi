# -*- coding: utf-8 -*-
"""中考真题取图通道：从 21 世纪教育网资源页的「资源预览」抓分页 PNG。

用法：
    python scripts/zk_preview.py 23236857            # 资源 id
    python scripts/zk_preview.py 23236857 --dir _zk/yn

实测结论（2026-11-28）：
  * 预览图直链在 preview.21cnjy.com，860px 宽，无水印，可匿名下载（带 Referer 即可）；
  * **每份资源只放前 5 页预览**，试卷后几页（综合题常在那儿）拿不到；
  * 题面是位图，没有文字层，取文字要么用 rapidocr 再人工校对（错字率不低），
    要么找公开转载的整卷文字版（更快更准）；
  * 七彩学科网(7cxk)、学科网组卷(zujuan.xkw.com) 都要登录/积分，直取拿不到内容；
    微信公众号文章正文需要登录态，同样取不到。

所以这个脚本只负责「把能白拿的那 5 页拿到手」，剩下的配图缺口要么等完整 PDF，
要么接受只能做前 5 页的题。
"""
import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def grab(rid, outdir):
    os.makedirs(outdir, exist_ok=True)
    url = 'https://zy.21cnjy.com/%s' % rid
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 900}, locale='zh-CN',
                            user_agent=UA)
        pg = ctx.new_page()
        pg.goto(url, wait_until='domcontentloaded', timeout=45000)
        pg.wait_for_timeout(3500)
        for _ in range(10):
            pg.mouse.wheel(0, 1200)
            pg.wait_for_timeout(400)
        title = pg.title()
        txt = pg.inner_text('body')
        imgs = pg.eval_on_selector_all(
            'img',
            'els=>els.map(e=>[e.currentSrc||e.src,e.naturalWidth,e.naturalHeight])')
        b.close()

    open(os.path.join(outdir, 'page.txt'), 'w', encoding='utf-8').write(txt)
    pv = [u for u, w, h in imgs if u and 'preview.21cnjy.com' in u]
    print('title:', title)
    print('preview pages:', len(pv))
    for i, u in enumerate(pv, 1):
        req = urllib.request.Request(u, headers={'User-Agent': UA,
                                                 'Referer': 'https://zy.21cnjy.com/'})
        data = urllib.request.urlopen(req, timeout=30).read()
        p = os.path.join(outdir, 'p%d.png' % i)
        open(p, 'wb').write(data)
        print('  p%d %6d B  %s' % (i, len(data), p))
    meta = {'id': rid, 'title': title, 'pages': len(pv), 'urls': pv}
    json.dump(meta, open(os.path.join(outdir, 'meta.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    return meta


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    rid = sys.argv[1]
    outdir = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == '--dir' \
        else os.path.join('_zk', re.sub(r'\W+', '', rid))
    grab(rid, outdir)


if __name__ == '__main__':
    main()
