# -*- coding: utf-8 -*-
"""并入 2025 年云南中考地理第 31 题（北京中轴线研学，6 分）。

题面与答案来自 2025 年云南省初中学业水平考试地理试卷（公开转载的官方卷，含参考答案与
评分标准）；配图裁自 21 世纪教育网该卷的免费预览页（_zk_probe/yunnan_5.png）。

说明：这套卷全 8 页，21cnjy 免费预览只放前 5 页，第 6—8 页的 32—36 题拿不到配图，
所以先只入第 31 题这一组；补齐需要完整 PDF。

运行：python scripts/add_yunnan_zk_2025.py
"""
import io
import json
import os
from PIL import Image

BANK = 'assets/bank/real.json'
FIG = 'assets/bank/fig'
SRC = 'E:/workbuddy/atlas-mundi/_zk_probe/yn31_raw.png'
YEAR, PAPER, EXAM = '2025', '云南中考', 'zk'
PROV, CITY = '云南', '全省统一'

Q31 = ('2024 年“北京中轴线”申遗成功。冬至这天，来自西安（34°N）的小云在北京（40°N）'
       '开展地理研学。研学手册上有“北京中轴线示意图”（图 1）、“冬至日正午乾清宫屋檐对'
       '太阳光照影响示意图”（图 2），读图回答问题。')

SUBS = [
    ('（1）小云参观完天坛后要前往紫禁城（故宫），紫禁城位于天坛的________方向。',
     '西北', 1),
    ('（2）当天正午前后，小云看到乾清宫内牌匾自西向东依次被地面金砖反射的阳光照亮，'
     '匾上最先被照亮的字是________。',
     '明', 1),
    ('（3）小云了解到乾清宫屋檐设计与太阳高度有关，她推测，同样的建筑在西安，若要使冬至'
     '正午室内光照面积相同，只需调整屋檐长度的话，则其长度应更________。',
     '短', 1),
    ('（4）小云量得研学手册上从永定门到钟鼓楼的中轴线，图上距离为 20 厘米，而实际距离约'
     '8 千米，则手册上的“北京中轴线示意图”比例尺为________。（数字式）',
     '1:40000（或 1/40000）', 1),
    ('（5）通过此次研学，小云了解到明清时期的北京城主要城市职能为________；一直以来，'
     '图中区域都不能建高层建筑，主要目的________。',
     '政治中心；保护古建筑（或保护传统文化）', 2),
]

EXPLAIN = {
    1: '图 1 有指向标（北朝上），天坛在城南、紫禁城在其北偏西，故为西北方向。',
    2: '冬至日太阳高度最低，阳光斜射入殿，自西向东依次照亮匾额横读的顺序，"明"字最靠西。',
    3: '西安纬度（34°N）低于北京（40°N），冬至正午太阳高度更大、进深更浅，屋檐要更短。',
    4: '8 km = 800000 cm，除以 20 cm 得 1:40000。',
    5: '明清北京城是全国政治中心；限制高度是为了保护中轴线与古都风貌（文物建筑）。',
}


def main():
    im = Image.open(SRC).convert('RGB')
    maxw = 1200
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    dst = os.path.join(FIG, 'yn2025zk-31.webp')
    im.save(dst, 'WEBP', quality=90, method=6)

    items = []
    for k, (q, ans, score) in enumerate(SUBS, 1):
        items.append({
            'id': 'yn2025zk-31-%d' % k,
            'type': 'material', 'lv': 'jr', 'grade': '初二', 'band': '初中',
            'exam': EXAM, 'year': YEAR, 'paper': PAPER, 'no': '31-%d' % k,
            'prov': PROV, 'city': CITY,
            'theme': '地球运动', 'cat': '真题',
            'tags': ['真题', '中考', '2025', '云南中考', '地球运动'],
            'diff': 4.6, 'score': score,
            'material': Q31, 'q': q, 'ansText': ans, 'exp': EXPLAIN[k],
            'opts': [], 'ans': -1,
            'src': '2025 云南中考 · 第 31 题',
            'figure': dst.replace(os.sep, '/'),
            'figureAlt': '图 1 北京中轴线示意图　图 2 冬至日正午乾清宫屋檐对太阳光照的影响',
            'figW': im.width, 'figH': im.height,
        })

    d = json.load(io.open(BANK, encoding='utf-8'))
    byid = {i['id']: i for i in d['items']}
    add = [i for i in items if i['id'] not in byid]
    for i in items:
        if i['id'] in byid:
            byid[i['id']].update(i)
    d['items'].extend(add)
    d['ver'] = '2026-11-28-real-20'
    io.open(BANK, 'w', encoding='utf-8', newline='').write(
        json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    print('云南中考新增 %d 小问，题库 %d 条' % (len(add), len(d['items'])))


if __name__ == '__main__':
    main()
