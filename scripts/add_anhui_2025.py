# -*- coding: utf-8 -*-
"""并入 2025 年安徽卷地理的非选择题（17—19，共 52 分）。

题面与答案取自原卷 PDF 文字层（_real/web/pdf/937_q.pdf），配图从内嵌图提取，未重绘。
18 题的图 1（如东位置）与图 2（光伏景观照片）在原卷里是两张独立位图，这里左右并排拼成一张；
18 题的（1）要求在给定的空白坐标图上手绘曲线，参考答案本身没有文字，故未入库。

注：原卷不标注每小题分值，按总分 52 分分配（17 题 18、18 题 13、19 题 21）。

运行：python scripts/add_anhui_2025.py
"""
import io
import json
import os
from PIL import Image

BANK = 'assets/bank/real.json'
FIG = 'assets/bank/fig'
SRC = 'E:/workbuddy/atlas-mundi/_ah/img'
YEAR, PAPER, EXAM = '2025', '安徽卷', 'gk'
PROV, CITY = '安徽', ''

Q17 = ('湘潭市是一座重要的钢铁工业城市。近年来该市积极转变发展思路，以“锰矿+锂云母”资源为基础，'
       '瞄准东部沿海地区新能源汽车及相关产业转移的机遇，通过“整车+电池+研发”全产业链布局，'
       '实施“链式承接”；同时与深圳高校共建异地联合实验室，将沿海地区研发成果在湘潭市孵化。'
       '下图示意湘潭市地理位置。')

Q18 = ('5 月某日，天气晴朗，某研学小组在江苏如东“光氢储一体化”海上光伏示范项目基地开展研学活动。'
       '当地利用大面积的滩涂，建设集海上光伏发电、制氢加氢和储能电站于一体的综合性项目，'
       '实现绿电就地消纳、转化应用。图 1 示意如东地理位置，图 2 为光伏项目景观照片。\n'
       '研学活动一　太阳高度角对太阳辐射的影响研究\n'
       '研学小组利用传感器测量当天到达地表的太阳辐射量日变化。\n'
       '研学活动二　光氢储一体化的必要性研究\n'
       '研学活动三　光伏项目带来的生态价值研究')

Q19 = ('通常把中高纬大陆冷空气突然向南爆发，南海一带东北风迅速加强的现象称为“冷涌”。'
       '2021 年 12 月 15—20 日，南海一带经历了一次强冷涌过程，马来西亚出现了持续性强降雨天气。'
       '下图表示北京时间 12 月 17 日 8 时海平面等压线分布，图中箭头示意此次冷涌气流移动路径。')

MATERIAL = [
    (17, Q17, ['ahB'], '湘潭市地理位置（城市、河流、铁路与省级界）', [
        ('（1）分析湘潭市围绕新能源汽车产业实施链式承接的地理位置优势。',
         '湘潭市靠近长沙，地处长株潭城市群，产业协同便利；距东部沿海地区适中，便于承接产业转移；'
         '有铁路等交通线，利于要素流通。',
         '读图取三条：靠长沙（城市群协同）、临东部沿海（便于承接）、有铁路（要素流通）。', 6),
        ('（2）从产业关联的角度，为湘潭市新能源汽车产业链式承接提出针对性策略，并简要说明理由。',
         '策略：依托“锰矿+锂云母”资源，发展电池原材料产业。\n'
         '理由：新能源汽车产业需大量电池，原材料产业是产业链基础，可降低成本、保障供应。',
         '“产业关联”就是上下游：本地有矿 → 先做电池原材料 → 接住整车厂的成本需求。', 6),
        ('（3）从创新发展的视角，为湘潭市新能源汽车产业高质量发展提出建议。',
         '建议：深化与深圳高校合作，完善异地联合实验室功能，加速研发成果转化；培育本地创新人才，'
         '打造产业创新平台，推动技术迭代。',
         '题干限“创新发展”，答案要落在研发、人才、平台，别写扩大产能。', 6),
    ], '产业与区域'),

    (18, Q18, ['ahC', 'ahD'],
     '图 1 如东地理位置　图 2 如东海上光伏项目景观', [
        ('（2）分析该项目实施光氢储一体化的必要性。',
         '受太阳辐射变化的影响，光伏发电不稳定；制氢可以消纳光电；储能电站可以储存氢能和光电。',
         '三步链：光电不稳 → 制氢消纳 → 储能兜底，缺一环就答不出“一体化”。', 6),
        ('（3）研学小组想从碳减排角度了解该光伏项目带来的生态价值，计划访谈相关生态环境专家，'
         '请为他们拟一份访谈提纲（要求至少列出 3 条）。',
         '一、光伏项目的发电功能对碳减排的影响；二、光伏项目对所在区域碳储量（生态系统）的影响；'
         '三、该地的生态环境现状及光伏项目的碳减排预期效果等。',
         '提纲要“问得到数”，每条都指向可量化的碳减排效果，不要写成泛泛的“谈谈意义”。', 7),
    ], '自然带与生态'),

    (19, Q19, ['ahG'], '12 月 17 日 8 时海平面等压线分布与冷涌气流路径', [
        ('（1）说明此次冷涌形成的动力条件。',
         '①蒙古—西伯利亚地区受强烈冷却，形成强盛的冷高压（亚洲高压），冷高压势力强大，冷空气堆积，'
         '气压梯度大，为冷空气南下提供强大动力；②冷高压南侧等压线密集，水平气压梯度力大，'
         '促使冷空气快速向南爆发；③冷空气向南移动过程中，受地转偏向力影响，逐渐形成偏北风，'
         '沿着亚洲东部的地形通道南下，加速冷涌的推进。',
         '三段递进：高压堆积 → 等压线密（梯度力大）→ 偏北风沿地形通道南下；读图要看等压线疏密。', 7),
        ('（2）指出冷涌南下过程中气流温湿性质的变化，并运用海—气相互作用原理解释其变化原因。',
         '变化：气流温度升高，湿度增大。\n'
         '原因：冷涌气流南下过程中，海面温度高于冷空气温度，海洋向大气输送热量，通过热传导的方式使'
         '冷空气增温；海洋表面水分蒸发，水汽进入冷空气中，使冷空气湿度增大，且冷空气受海洋加热后，'
         '空气对流运动增强，进一步促进水汽的输送和混合，导致冷涌气流湿度增加。',
         '先定性（升温增湿），再用“海面比空气暖 → 感热输送 + 蒸发供水汽”两步解释。', 7),
        ('（3）结合材料，分析马来西亚此次强降雨的成因。',
         '①冷涌带来的冷空气与当地暖湿空气相遇，形成冷暖气团交汇，暖湿空气被迫抬升，水汽冷却凝结'
         '形成降水；②冷涌气流势力强，推动暖湿空气强烈上升，垂直上升运动显著，水汽快速凝结成云致雨，'
         '降水强度大；③冷涌持续时间较长（12 月 15—20 日），使得暖湿空气持续抬升，降水持续时间长，'
         '累计降水量大。',
         '从“为什么下雨（锋面抬升）—为什么下得猛（上升强）—为什么下得久（持续期长）”三层展开。', 7),
    ], '大气与天气'),
]


def side_by_side(paths, dst, gap=80, maxw=1500):
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
        dst = os.path.join(FIG, 'ah2025-%d.webp' % no)
        if len(figs) == 1:
            size[no] = to_webp(os.path.join(SRC, figs[0] + '.png'), dst)
        else:
            size[no] = side_by_side([os.path.join(SRC, f + '.png') for f in figs], dst)

    items = []
    for no, mat, figs, figalt, subs, theme in MATERIAL:
        for k, (q, ans, exp, score) in enumerate(subs, 1):
            items.append({
                'id': 'ah2025-%d-%d' % (no, k),
                'type': 'material', 'lv': 'sr', 'grade': '高三', 'band': '高中',
                'exam': EXAM, 'year': YEAR, 'paper': PAPER, 'no': '%d-%d' % (no, k),
                'prov': PROV, 'city': CITY,
                'theme': theme, 'cat': '真题',
                'tags': ['真题', '2025', '安徽卷', theme],
                'diff': 6.3, 'score': score,
                'material': mat, 'q': q, 'ansText': ans, 'exp': exp,
                'opts': [], 'ans': -1,
                'src': '2025 安徽卷 · 第 %d 题' % no,
                'figure': os.path.join(FIG, 'ah2025-%d.webp' % no).replace(os.sep, '/'),
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
    d['ver'] = '2026-11-28-real-18'
    io.open(BANK, 'w', encoding='utf-8', newline='').write(
        json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    print('安徽卷新增 %d 小问，题库 %d 条' % (len(add), len(d['items'])))


if __name__ == '__main__':
    main()
