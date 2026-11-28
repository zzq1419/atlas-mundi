# -*- coding: utf-8 -*-
"""并入 2025 年福建卷（高考）地理的非选择题（17—19，共 52 分）。

题面与答案取自原卷 PDF 文字层（_real/web/pdf/1005_q.pdf），配图从内嵌图提取，未重绘。
17 题的「左图（流域）+ 右图（建设方案）」在原卷里是两张位图，这里左右并排拼成一张。

注：原卷不标注每小题分值。这里的 score 是折算后的「掌握分」（0—10），
不是原始分值 —— 原始分值放到 score 里会被难度区间过滤掉（19 题 16 分整题就消失过）。
按总分 52 分折算：17 题 18、18 题 18、19 题 16 → 掌握分 6/6/6/6/6/6/7。

运行：python scripts/add_fujian_gk_2025.py
"""
import io
import json
import os
from PIL import Image

BANK = 'assets/bank/real.json'
FIG = 'assets/bank/fig'
SRC = 'E:/workbuddy/atlas-mundi/_fjgk/img'
YEAR, PAPER, EXAM = '2025', '福建卷', 'gk'
PROV, CITY = '福建', ''

Q17 = ('我国东南某流域（下左图）在台风影响下，暴雨、山洪和风暴潮叠加，易出现严重内涝。'
       '当地政府采取了诸多防灾减灾措施，工作初见成效。政府拟按海绵城市理念，完善城镇建设方案；'
       '改变传统的筑坝挡潮方式，将临近海岸的水网开放为潮流通道，使部分区域形成红树林湿地，'
       '助力打造休闲文旅带。')

Q18 = ('大西洋中 Y 火山岛（下图）上，火山熔岩在海岸形成陡崖，因火山地貌典型多样，该岛入选'
       '联合国教科文组织世界地质公园名录。为保障电力供应稳定，该岛采用风能和水能协调发电，'
       '其中水电由蓄能电站（利用风电抽取海水到蓄水池，再适时利用蓄水发电）提供。'
       '该岛拟合理开发西南海域旅游资源。')

Q19 = ('服务业在进行区位选择时必须考虑人口规模、交通因素以及被服务对象的需求与分布等。'
       '某区域（下图）致力打造 15 分钟运动圈，新建了一个运动场馆。这一场馆主要服务该区域居民，'
       '开放时段为 6:00—11:30，14:00—22:00。')

MATERIAL = [
    (17, Q17, ['f41', 'f42'],
     '左图 某流域地形与水网　右图 某地建设方案（①雨水花园 ②荒草地建游乐场 ③裸地改绿地）', [
        ('（1）从地形角度，分析台风产生的暴雨易在该流域造成内涝的原因。',
         '台风受地形阻挡和抬升，降雨量增多；盆地周围坡度大，汇水快；中间地势低平，排水不畅。',
         '三段式：地形抬升致雨多 → 四周坡陡汇水快 → 中间低平排不掉。', 6),
        ('（2）右图为某地建设方案（包括①、②和③三种做法），选出不利于削减下游洪峰的做法，'
         '并说明理由。',
         '②。理由：不透水面积增大，降水难以向土壤下渗，土壤蓄水减少，汇入下游河道水量变大、'
         '汇入速度加快。',
         '只有②是硬化地面（游乐场），其余两项都是增加下渗的海绵化做法。', 6),
        ('（3）与传统的大规模筑坝挡潮方式相比，举出将临近海岸的水网开放为潮流通道产生的三点'
         '经济效益。',
         '节省建设和维护大坝的费用；增加旅游收入；提高生态系统服务价值，具有潜在的经济效益；'
         '受益地区土地增值。',
         '注意问的是“经济效益”：省钱、赚钱、地价涨，生态价值那条要落到“潜在经济效益”上。', 6),
    ], '水与海洋'),

    (18, Q18, ['f45'], 'Y 火山岛地形、城镇与甲乙海岸剖面', [
        ('（1）甲、乙海岸的火山熔岩形成于同一时期。分别指出甲、乙的海岸侵蚀地貌类型，'
         '并从位置角度说明甲、乙海岸侵蚀作用的强弱。',
         '甲：海蚀平台。乙：海蚀崖。\n'
         '甲位于东北信风迎风处，乙位于背风处；与乙相比，甲风力较强，海浪较大，'
         '受到海浪的侵蚀较强。\n'
         '（或：甲位于东北信风迎风处，乙位于背风处；与甲相比，乙风力较弱，海浪较小，'
         '受到海浪的侵蚀较弱。）',
         '先定地貌名（平台 vs 陡崖），再用“迎风/背风 → 风浪大小 → 侵蚀强弱”一条链说明。', 6),
        ('（2）从①②两地选择更适合建设蓄能电站的地点，并给出选择依据。',
         '地点：①。依据：地势起伏较小，建设空间较大；距中心城镇较近且周边城镇较多，'
         '更好满足用电需求；距风电场较近，建设成本较小。',
         '蓄能电站要“有平地放水池、离负荷近、离电源近”，从等高线疏密和城镇分布读数。', 6),
        ('（3）为该岛西南海域的旅游宣传提供两个能体现海水特色的关键词，并分别说明理由。',
         '海水清澈（或透明度高）：西南部城镇少，西南海域受人类活动干扰小；'
         '海水温度适宜：纬度较低；碧波荡漾：晴朗天气多，风浪小；水质洁净：入海径流少，'
         '陆源污染少。',
         '开放题，任选两个词即可，但每个词的理由必须指向“海水”而不是“沙滩”“阳光”。', 6),
    ], '地表形态'),

    (19, Q19, ['f46'], '某区域运动场馆、居住小区、道路、公交与共享单车点分布', [
        ('请你设计一份调查方案（包括调查对象、调查方法、调查内容等），调查目标如下：'
         '①该场馆能否满足该区域居民的不同运动需求；②该区域具有运动需求的居民在 15 分钟'
         '出行时间内能否到达该场馆。',
         '调查对象：运动场馆、居民。\n'
         '调查方法：实地调查运动场馆、交通站点、线路情况等；向小区居民发放调查问卷；'
         '对运动场馆内的健身居民与管理人员等进行访谈。\n'
         '调查内容：场馆提供的运动项目和数量、容纳能力、运动时间、运动器械使用情况等；'
         '小区居民人数、运动项目偏好、运动时段、出行方式和出行时间等。\n'
         '数据处理：应用 GIS 等方法，通过数据处理，估算该区域到该场馆运动的居民人数、'
         '运动项目偏好、运动时段和出行时间。\n'
         '结果分析：根据调查结果，回答调查目标中的问题，例如该场馆提供的运动项目、容纳能力'
         '与到该场馆居民的运动项目偏好和人数是否匹配。',
         '方案题按“对象—方法—内容—处理—分析”五段写，缺“数据处理”和“结果分析”会丢分；'
         '还要保证每个环节都能回答题干的两个目标。', 7),
    ], '人口与城市'),
]


def side_by_side(paths, dst, gap=90, maxw=1600):
    ims = [Image.open(p).convert('RGB') for p in paths]
    h = max(i.height for i in ims)
    ims = [i.resize((round(i.width * h / i.height), h), Image.LANCZOS) for i in ims]
    W = sum(i.width for i in ims) + gap * (len(ims) - 1)
    cv = Image.new('RGB', (W, h), 'white')
    x = 0
    for i in ims:
        cv.paste(i, (x, 0))
        x += i.width + gap
    if cv.width > maxw:
        cv = cv.resize((maxw, round(cv.height * maxw / cv.width)), Image.LANCZOS)
    cv.save(dst, 'WEBP', quality=88, method=6)
    return cv.size


def to_webp(src, dst, maxw=1200):
    im = Image.open(src).convert('RGB')
    if im.width > maxw or im.height > 1100:
        sc = min(maxw / im.width, 1100 / im.height, 1)
        im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
    im.save(dst, 'WEBP', quality=88, method=6)
    return im.size


def main():
    size = {}
    for no, mat, figs, figalt, subs, theme in MATERIAL:
        dst = os.path.join(FIG, 'fjgk2025-%d.webp' % no)
        if len(figs) == 1:
            size[no] = to_webp(os.path.join(SRC, figs[0] + '.png'), dst)
        else:
            size[no] = side_by_side([os.path.join(SRC, f + '.png') for f in figs], dst)

    items = []
    for no, mat, figs, figalt, subs, theme in MATERIAL:
        for k, (q, ans, exp, score) in enumerate(subs, 1):
            items.append({
                'id': 'fjgk2025-%d-%d' % (no, k),
                'type': 'material', 'lv': 'sr', 'grade': '高三', 'band': '高中',
                'exam': EXAM, 'year': YEAR, 'paper': PAPER, 'no': '%d-%d' % (no, k),
                'prov': PROV, 'city': CITY,
                'theme': theme, 'cat': '真题',
                'tags': ['真题', '2025', '福建卷', theme],
                'diff': 6.3, 'score': score,
                'material': mat, 'q': q, 'ansText': ans, 'exp': exp,
                'opts': [], 'ans': -1,
                'src': '2025 福建卷 · 第 %d 题' % no,
                'figure': os.path.join(FIG, 'fjgk2025-%d.webp' % no).replace(os.sep, '/'),
                'figureAlt': figalt,
                'figW': size[no][0], 'figH': size[no][1],
            })

    d = json.load(io.open(BANK, encoding='utf-8'))
    byid = {i['id']: i for i in d['items']}
    add = [i for i in items if i['id'] not in byid]
    for i in items:
        if i['id'] in byid:
            byid[i['id']].update(i)
    d['items'].extend(add)
    d['ver'] = '2026-11-28-real-21'
    io.open(BANK, 'w', encoding='utf-8', newline='').write(
        json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    print('福建卷（高考）新增 %d 小问，题库 %d 条' % (len(add), len(d['items'])))


if __name__ == '__main__':
    main()
