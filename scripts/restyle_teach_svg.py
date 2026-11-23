# -*- coding: utf-8 -*-
"""把知识卡里的示意图从"深色主题 SVG"改成白底黑字的课本插图风格。

只做一次颜色/底色迁移，不改任何坐标和文字：
  · 每张图最前面插一块白底（原来的 SVG 是透明的，靠深色卡片透出来）
  · 所有浅色墨色映射成深色（#cfdff2 → #1a1f28 这一类）
  · 半透明的彩色填充保持色相，压深一档，在白底上才看得清
为什么用"后处理"而不是改生成脚本：图是三个脚本（_svg_gen / _svg_more /
_svg_var）加上更早的 _svg_upgrade 分别产出的，颜色散在几十处硬编码里，
挨个改必漏。这里按颜色值统一查表，一次覆盖全部。
"""
import io
import json
import re
import sys

P = 'index.html'

# 实色：深色主题的墨 → 白底黑字的墨
SOLID = {
    '#cfdff2': '#1a1f28',   # 正文
    '#8ba1bd': '#374151',   # 次要
    '#6f86a4': '#6b7280',   # 更弱
    '#ef9d7f': '#c0453a',   # 暖（升温、暖流）
    '#8fb8de': '#2f6f9e',   # 冷（降温、寒流）
    '#f0c987': '#a67c1f',   # 强调（金）
}

# rgba(r,g,b,a) 的 rgb 三元组 → 新三元组。第二项是透明度倍数。
RGB = {
    (239, 157, 127): ((192, 69, 58), 1.35),
    (143, 184, 222): ((47, 111, 158), 1.35),
    (240, 201, 135): ((166, 124, 31), 1.35),
    (126, 158, 96): ((120, 156, 84), 1.45),
    (150, 180, 110): ((104, 134, 66), 1.2),
    (58, 104, 152): ((70, 118, 165), 1.45),
    (92, 148, 198): ((80, 128, 172), 1.2),
    (140, 170, 210): ((52, 74, 100), 1.5),   # 线条/边框/网格
    (255, 255, 255): ((26, 40, 58), 0),      # 单独处理，见 conv_rgba
    (207, 223, 242): ((60, 80, 105), 1.0),
    (198, 218, 242): ((60, 80, 105), 1.0),
    (230, 240, 252): ((38, 54, 74), 1.2),
    (170, 160, 110): ((150, 120, 60), 1.0),
    (150, 140, 86): ((150, 120, 60), 1.0),
    (120, 170, 120): ((90, 130, 80), 1.0),
}

RE_RGBA = re.compile(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)')


def conv_rgba(m):
    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    a = float(m.group(4))
    # 原来的"半透明白"在白底上有两副面孔：面板底（alpha 0.02~0.05）只需要
    # 一点点灰就够，云和气团（alpha 0.4~0.7）却必须留住存在感 ——
    # 一条统一倍数要么把面板涂成灰板，要么让云彻底消失。
    if (r, g, b) == (255, 255, 255):
        na = min(0.10, a * 3.0) if a <= 0.08 else min(1.0, a * 1.15)
        return 'rgba(26,40,58,%s)' % (('%.2f' % na).rstrip('0').rstrip('.') or '0')

    hit = RGB.get((r, g, b))
    if not hit:
        if lum(r, g, b) < 190:
            return m.group(0)
        # 没在表里的浅色（各种偏白的填充/文字）：压深，透明度略提
        return 'rgba(%d,%d,%d,%s)' % (int(r * 0.18), int(g * 0.18), int(b * 0.18),
                                      ('%.2f' % min(1.0, a * 1.4)).rstrip('0').rstrip('.') or '0')
    (nr, ng, nb), k = hit
    na = min(1.0, a * k)
    return 'rgba(%d,%d,%d,%s)' % (nr, ng, nb, ('%.2f' % na).rstrip('0').rstrip('.') or '0')


RE_HEX = re.compile(r'#([0-9a-fA-F]{6})')


def lum(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def conv_hex(m):
    """剩下没在表里的实色：凡是接近白的（浅字、浅描边、浅填充）一律压深。

    深色版里"比底色亮"的东西，到白底上必须"比底色暗"，否则直接消失 ——
    fronts 那张的云和气团第一版就是这样，椭圆还在、里面的字没了。
    已经映射过的正文色（#374151 亮度 64）不会被二次处理。
    """
    h = m.group(1)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if lum(r, g, b) < 185:
        return m.group(0)
    f = 0.16
    return '#%02x%02x%02x' % (int(r * f), int(g * f), int(b * f))


def restyle(svg):
    if not svg.startswith('<svg'):
        return svg
    # 1) 先转色（这一步会把纯白也压深，所以白底必须放在后面才插）
    for o, n in SOLID.items():
        svg = svg.replace(o, n)
        svg = svg.replace(o.upper(), n)
    svg = RE_HEX.sub(conv_hex, svg)
    svg = RE_RGBA.sub(conv_rgba, svg)
    # 2) 白底：插在 <svg ...> 之后。尺寸按 viewBox 取，别写死 560×300
    if 'data-bg' not in svg:
        m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
        w, h = (m.group(1), m.group(2)) if m else ('560', '300')
        head_end = svg.index('>', svg.index('<svg')) + 1
        svg = (svg[:head_end] + '<rect data-bg="1" x="0" y="0" width="%s" height="%s" fill="#ffffff"/>' % (w, h)
               + svg[head_end:])
    return svg


def main():
    s = io.open(P, encoding='utf-8', newline='').read()
    lines = s.split('\r\n')
    mi = [i for i, l in enumerate(lines) if l.startswith('  var TEACH_MEDIA = {')][0]
    line = lines[mi]
    pre = '  var TEACH_MEDIA = '
    body = line[len(pre):]
    obj, end = json.JSONDecoder().raw_decode(body)
    tail = body[end:]
    n = 0
    for k, v in obj.items():
        if isinstance(v, str) and v.startswith('<svg'):
            nv = restyle(v)
            if nv != v:
                n += 1
            obj[k] = nv
    lines[mi] = pre + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + tail
    io.open(P, 'w', encoding='utf-8', newline='').write('\r\n'.join(lines))
    print('改造 %d / %d 张示意图' % (n, len(obj)))

    # 巡检：还有没有漏网的深色墨
    left = {}
    for k, v in obj.items():
        for c in ('#cfdff2', '#8ba1bd', '#6f86a4', 'rgba(255,255,255', 'rgba(140,170,210'):
            if c in v:
                left.setdefault(c, []).append(k)
    if left:
        print('!! 仍有残留:', {c: len(v) for c, v in left.items()})
        for c, ks in left.items():
            print('   ', c, ks[:4])
    else:
        print('无残留')


main()
