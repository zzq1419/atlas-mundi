# -*- coding: utf-8 -*-
"""并入 2025 年天津卷地理的非选择题（16—18，共 55 分）。

题面与答案取自原卷 PDF 文字层（_real/web/pdf/930_q.pdf），配图从内嵌图提取，未重绘。
17、18 题各含两幅图，按原卷左右并排拼成一张。

注：原卷不标注每小题分值，按总分 55 分分配（16 题 18、17 题 19、18 题 18）。

运行：python scripts/add_tianjin_2025.py
"""
import io
import json
import os
from PIL import Image

BANK = 'assets/bank/real.json'
FIG = 'assets/bank/fig'
SRC = 'E:/workbuddy/atlas-mundi/_tj/img'
YEAR, PAPER, EXAM = '2025', '天津卷', 'gk'
PROV, CITY = '天津', ''

Q16 = ('下图为齐齐哈尔市及附近地区位置示意图。\n'
       '1954 年，中国一重集团有限公司的前身——第一重型机器厂在富拉尔基建厂。')

Q17 = ('赤水河发源于云贵高原，在四川省合江县汇入长江，流域内上游地区以喀斯特地貌为主；'
       '下游地区丹霞地貌发育，分布有国家森林公园。该流域是著名的“美酒河”，但流域内经济发展'
       '不均衡，还出现了河水污染、水土流失、生态退化等问题。近些年，云贵川三省采取流域生态'
       '补偿机制，让受益者支付，保护者受偿，通过共同治理，流域生态环境持续向好。\n'
       '下图为图 1 赤水河流域示意图、图 2 赤水河流域部分市（县）用水量与人均 GDP 示意图。')

Q18 = ('下图为黑山及周边国家位置示意图。\n'
       '中黑合作建设的莫祖拉风电场位于南部山区，该风电场建设过程中克服了来自亚得里亚海的'
       '“盐雾”影响。')

MATERIAL = [
    (16, Q16, ['tj16a'], '齐齐哈尔市及附近地区位置示意图（嫩江、滨洲铁路、富拉尔基区）', [
        ('（1）分析第一重型机器厂在该地建厂的有利条件。',
         '靠近嫩江，水源充足；地处松嫩平原，地形平坦开阔（土地资源丰富）；有滨洲铁路穿过，'
         '交通便利；依托齐齐哈尔，工业基础好。',
         '读图取三条（水、地形、铁路），再补一条材料外的（老工业基地基础），别只抄图。', 6),
        ('（2）说明发展“吃配”型工业经济对该区产业发展的积极影响。',
         '扩大产业规模（带动相关产业发展）；调整原有产业结构（完善本地产业链布局）；'
         '推动相关产业技术升级和产品创新；加强分工协作，降低生产成本。',
         '“吃配”= 给大企业做配套：规模、结构、技术、成本四条顺着产业链写。', 6),
        ('（3）从可持续发展角度，为富拉尔基的城市更新提出建议。',
         '形成多元化产业格局；修复和整治生态环境；完善基础设施建设。',
         '可持续发展三支点：经济（产业多元）、生态（环境整治）、社会（基础设施）。', 6),
    ], '产业与区域'),

    (17, Q17, ['tj17b', 'tj18a'],
     '图 1 赤水河流域示意图（丹霞地貌、水文站、酒厂）　图 2 各市（县）用水量与人均 GDP', [
        ('（1）分析赤水河下游丹霞地貌区生物多样性丰富的自然原因。',
         '地处亚热带季风气候区，水热条件好；地形复杂，水热组合状况多样；高差变化显著，'
         '水热条件垂直差异明显。',
         '三条都指向“水热组合多样”：气候打底、地形分化、垂直分异。', 7),
        ('（2）通过甲、乙两水文站的观测发现，甲站的上游地区地表侵蚀度更大。从甲站角度推测原因。',
         '地面坡度大；植被覆盖率较低；土壤结构松散（地表破碎）；降水强度大（坡面径流量大）。',
         '侵蚀四要素：坡度、植被、土质、降水强度，逐条对着甲站上游答。', 6),
        ('（3）结合图 1，判断图 2 中哪个市（县）是受益者，并分析其要对流域保护者进行生态补偿的原因。',
         '受益者：仁怀市。\n'
         '原因：仁怀市发展白酒产业用水量大，对水质要求高，限制了上游市县产业发展；'
         '对水质有污染，会对下游产业发展造成不利影响；白酒产业产值高，受益大（有经济补偿能力）。',
         '图 2 里仁怀“高人均 GDP + 大用水量”一眼可辨；理由要写清“受益—影响—有能力补偿”三层。', 6),
    ], '自然带与生态'),

    (18, Q18, ['tj18b', 'tj18c'],
     '黑山及周边国家位置示意图　能源不可能三角形示意图', [
        ('（1）分析黑山沿岸海域海水盐度高的原因。',
         '该地沿岸为地中海气候区，夏季高温少雨，蒸发强；沿岸山脉阻挡河流汇入，入海径流量少；'
         '海区比较封闭，海水与外界交换少，盐度高。',
         '盐度三因素：蒸发强、淡水汇入少、海区封闭，缺一条都不完整。', 6),
        ('（2）分别说明该铁路建成后对黑山、塞尔维亚和我国的意义。',
         '对黑山：完善交通网，沟通南北，带动区域经济发展。\n'
         '对塞尔维亚：打通出海通道，方便与地中海沿岸国家的交往和贸易。\n'
         '对我国：促进我国与欧洲国家的联系和合作，提高我国的国际影响力'
         '（促进我国“一带一路”倡议在欧洲的发展和落实）。',
         '三方分写，各一到两句：黑山要“连通”，塞尔维亚要“出海口”，我国要“合作与影响力”。', 6),
        ('（3）黑山要破解能源困局，应采取哪些措施？',
         '能源组合多元化，提供稳定的电能；在能源生产时要注意减少对生态环境的破坏；'
         '提高技术水平，提升发电效率。',
         '“不可能三角”里三个角（清洁、可靠、经济）不能同时满足，措施就是靠多元、环保、提效去缓解。', 6),
    ], '交通与区位'),
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
    if im.width > maxw or im.height > 1200:
        sc = min(maxw / im.width, 1200 / im.height, 1)
        im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
    im.save(dst, 'WEBP', quality=86, method=6)
    return im.size


def main():
    size = {}
    for no, mat, figs, figalt, subs, theme in MATERIAL:
        dst = os.path.join(FIG, 'tj2025-%d.webp' % no)
        if len(figs) == 1:
            size[no] = to_webp(os.path.join(SRC, figs[0] + '.png'), dst)
        else:
            size[no] = side_by_side([os.path.join(SRC, f + '.png') for f in figs], dst)

    items = []
    for no, mat, figs, figalt, subs, theme in MATERIAL:
        for k, (q, ans, exp, score) in enumerate(subs, 1):
            items.append({
                'id': 'tj2025-%d-%d' % (no, k),
                'type': 'material', 'lv': 'sr', 'grade': '高三', 'band': '高中',
                'exam': EXAM, 'year': YEAR, 'paper': PAPER, 'no': '%d-%d' % (no, k),
                'prov': PROV, 'city': CITY,
                'theme': theme, 'cat': '真题',
                'tags': ['真题', '2025', '天津卷', theme],
                'diff': 6.4, 'score': score,
                'material': mat, 'q': q, 'ansText': ans, 'exp': exp,
                'opts': [], 'ans': -1,
                'src': '2025 天津卷 · 第 %d 题' % no,
                'figure': os.path.join(FIG, 'tj2025-%d.webp' % no).replace(os.sep, '/'),
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
    d['ver'] = '2026-11-28-real-16'
    io.open(BANK, 'w', encoding='utf-8', newline='').write(
        json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    print('天津卷新增 %d 小问，题库 %d 条' % (len(add), len(d['items'])))


if __name__ == '__main__':
    main()
