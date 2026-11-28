# -*- coding: utf-8 -*-
"""并入 2025 年贵州卷地理的非选择题（17—19，共 52 分）。

题面与答案取自原卷 PDF 文字层（_real/web/pdf/971_q.pdf），配图从内嵌图提取，未重绘。
18 题的图 1、图 2 在 PDF 里是两张独立位图，这里按原卷左右并排拼成一张。

注：原卷不标注每小题分值，按总分 52 分分配（17 题 18、18 题 18、19 题 16）。

运行：python scripts/add_guizhou_2025.py
"""
import io
import json
import os
from PIL import Image

BANK = 'assets/bank/real.json'
FIG = 'assets/bank/fig'
SRC = 'E:/workbuddy/atlas-mundi/_gz/img'
YEAR, PAPER, EXAM = '2025', '贵州卷', 'gk'
PROV, CITY = '贵州', ''

Q17 = ('为探索现代农业可持续发展之路，2009 年以来，在高校、企业以及政府的协作带动下，'
       '全国陆续建成 1800 多家科技小院。科技小院常驻生产地，科研人员在田间地头进行科学研究和'
       '技术推广，帮助农民解决实际问题。近年来，相关企业通过组织全国科技强农创新大赛、'
       '完善优质农产品供销体系等措施促进科技小院科研成果转化，助力乡村振兴。四川省丹棱县是'
       '我国最大的桔橙生产地之一，在丹棱桔橙科技小院及相关企业的助力下，所产桔橙品质更加优良、'
       '稳定，农业效益及可持续发展能力显著提高。下图示意丹棱县位置。')

Q18 = ('我国西南喀斯特山区地表蓄水能力通常较弱，水资源利用率较低（水资源利用率是区域用水量在'
       '水资源可利用总量中的占比）。图 1 示意某地喀斯特地貌剖面及降雨径流过程，图 2 示意该地区'
       '地下河出口处某时段实测降雨及径流响应的两种模拟曲线。')

Q19 = ('甲烷是大气中主要的温室气体之一。三沙湾是福建省重要的水产养殖区，从河口向海依次为'
       '河口养殖区、中部限养区、湾口养殖区。该区域通过水面释放的甲烷主要来源于缺氧条件下水体'
       '和沉积物中有机物的降解，其释放量主要受陆源径流输入、温度、投饵量等因素的影响。'
       '下图为 2023 年三沙湾表层水体甲烷释放量的时空变化。')

MATERIAL = [
    (17, Q17, 'gz2025-17.webp', '四川省及丹棱县位置、河流与山地分布', [
        ('（1）简析丹棱县桔橙品质稳定的原因。',
         '亚热带湿润山区，水热条件充足，利于桔橙生长，自然条件优越，生态调节能力强；'
         '科技小院助力；相关企业助力。',
         '自然条件（水热 + 山区生态）打底，再加科技小院与企业两个“人”的因素。', 6),
        ('（2）说明科技小院常驻生产地对其技术推广的益处。',
         '科技小院接近产地，利于及时了解农业的生产技术需求，提高科技小院技术研发的针对性和实用性；'
         '就近研发，可以提高科技小院技术转化效率；增进科技小院与农户的交流，利于技术的推广等。',
         '三个“近”：近需求 → 研发对路；近田间 → 转化快；近农户 → 推广顺。', 6),
        ('（3）分析企业组织科技强农创新大赛、完善优质农产品供销体系对促进农业可持续发展的作用。',
         '创新大赛可以促进技术交流，最终促进科研水平及技术水平的提高、科研能力的进步；'
         '农业技术的进步可降低生态破坏；完善供销体系可以扩大农产品市场，提高农业收益；'
         '完善供销体系利于掌握需求，提高农产品市场适应性等。',
         '两件事分开答：大赛管“技术—生态”，供销体系管“市场—收益—适应性”。', 6),
    ], '产业与区域'),

    (18, Q18, 'gz2025-18.webp', '图 1 喀斯特地貌剖面与降雨径流过程　图 2 降雨与两种径流响应曲线', [
        ('（1）指出图 2 中更符合流量实测情况的曲线并说明理由。',
         '曲线Ⅰ更符合实测情况。理由：裂隙、溶洞及地下通道发育，地表水大量下渗；'
         '地下水排泄快，流量变化剧烈，陡涨陡落等。',
         '先给结论（Ⅰ），再用“下渗强 + 排泄快”解释陡涨陡落，结论与理由要一一对应。', 6),
        ('（2）分析该区域地表蓄水能力弱的原因。',
         '岩石裂隙发育，下渗强；土层薄，蓄水能力弱；植被稀少，截留作用弱等。',
         '“漏得快（岩石）—存不住（土层薄）—拦不住（植被少）”，三条各指一个环节。', 6),
        ('（3）从资源开发的角度，提出喀斯特山区提高水资源利用率的措施。',
         '修建水库等储水设施，增强地表蓄水能力；加强水资源的勘查；合理利用地下水等。',
         '注意题干限“资源开发角度”，答“节约用水”这类属于消费端，容易跑偏。', 6),
    ], '水与海洋'),

    (19, Q19, 'gz2025-19.webp', '三沙湾三个养殖区四季表层水体甲烷释放量柱状图', [
        ('（1）归纳三沙湾海域表层水体甲烷释放量的时空变化特征。',
         '从时间上看，甲烷释放量夏季明显高于其他季节；从空间上看，在不同季节，'
         '河口养殖区均高于其他养殖区等。',
         '“时空”两字要分别落到句子上：先说时间（夏高），再说空间（河口高），不要混成一句。', 6),
        ('（2）分析影响河口养殖区夏季甲烷释放量的主要原因。',
         '夏季河流带来大量有机物；夏季鱼类生长快，饵料投放多，水体有机物多；'
         '夏季水温高，有机物降解快等。',
         '有机物“来源”（径流 + 投饵）与“降解速度”（高温）两头都答，缺一头扣分。', 5),
        ('（3）为三沙湾低碳养殖提出合理建议。',
         '工程类措施主要包括：科学喂养，减少水体中有机物；优化养殖结构和养殖密度。'
         '非工程类措施主要指：加强甲烷释放量同步监测，科学指导产业规划和近岸海域综合开发等。',
         '按“工程／非工程”分类作答，比零散列点更容易拿满。', 5),
    ], '自然带与生态'),
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
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    im.save(dst, 'WEBP', quality=86, method=6)
    return im.size


def main():
    size = {}
    size[17] = to_webp(os.path.join(SRC, 'gz17.png'), os.path.join(FIG, 'gz2025-17.webp'))
    size[18] = side_by_side([os.path.join(SRC, 'gz18a.png'), os.path.join(SRC, 'gz18b.png')],
                            os.path.join(FIG, 'gz2025-18.webp'))
    size[19] = to_webp(os.path.join(SRC, 'gz19.png'), os.path.join(FIG, 'gz2025-19.webp'))

    items = []
    for no, mat, fig, figalt, subs, theme in MATERIAL:
        for k, (q, ans, exp, score) in enumerate(subs, 1):
            items.append({
                'id': 'gz2025-%d-%d' % (no, k),
                'type': 'material', 'lv': 'sr', 'grade': '高三', 'band': '高中',
                'exam': EXAM, 'year': YEAR, 'paper': PAPER, 'no': '%d-%d' % (no, k),
                'prov': PROV, 'city': CITY,
                'theme': theme, 'cat': '真题',
                'tags': ['真题', '2025', '贵州卷', theme],
                'diff': 6.2, 'score': score,
                'material': mat, 'q': q, 'ansText': ans, 'exp': exp,
                'opts': [], 'ans': -1,
                'src': '2025 贵州卷 · 第 %d 题' % no,
                'figure': os.path.join(FIG, fig).replace(os.sep, '/'),
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
    d['ver'] = '2026-11-28-real-14'
    io.open(BANK, 'w', encoding='utf-8', newline='').write(
        json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    print('贵州卷新增 %d 小问，题库 %d 条' % (len(add), len(d['items'])))


if __name__ == '__main__':
    main()
