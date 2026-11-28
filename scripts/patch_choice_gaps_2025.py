# -*- coding: utf-8 -*-
"""补齐 2025 卷里漏掉的选择题：天津 11—13、甘肃 9—10。

这两处当初导选择题时被跳过（天津这组材料跨页、甘肃这组带跨页表格），
结果就是「卷面 15 题、题库只有 12 题」这种对不上的情况。发现方式：
按 (年,卷) 收集 choice 的 no，看 1..max 里缺哪几号。

运行：python scripts/patch_choice_gaps_2025.py
"""
import io
import json
import os
from PIL import Image

BANK = 'assets/bank/real.json'
FIG = 'assets/bank/fig'
SRC_TJ = 'E:/workbuddy/atlas-mundi/_tj/img'
YEAR = '2025'

# ---------------------------------------------------------------- 天津
TJ_MAT = ('为促进成渝双城经济圈高质量发展，两地共建了全国首个跨省新区——高竹新区。'
          '新区内布局了先进制造业、高品质住宅、生态康养和都市农业等功能区（下图）。'
          '读图文材料，完成下面小题。')
TJ13 = ('红树林是蓝碳生态系统的重要组成部分，保护红树林对促进生态文明建设具有重要意义。')

TJ = [
    (11, TJ_MAT, 't89', '高竹新区功能区分布示意图（①②③④四个功能区）', '产业与区域',
     '影响高竹新区选址的主要因素是（　　）',
     ['国家政策', '人口数量', '生活成本', '基础设施'], 0,
     '“全国首个跨省新区”是政策直接推动的产物，选址首先要看国家与两地政府的战略安排。', 5.0),
    (12, TJ_MAT, 't89', '高竹新区功能区分布示意图（①②③④四个功能区）', '产业与区域',
     '关于新区内部各功能区布局及原因的描述，正确的是（　　）',
     ['①都市农业区——靠近公路，便于产品运输',
      '②生态康养区——依山傍水，生态环境良好',
      '③先进制造业区——土地集中连片，利于产业集聚',
      '④高品质住宅区——地形平坦开阔，开发成本较低'], 2,
     '读图：③位于新区中部、被高速公路与核心区边界围合的连片平地上，最符合先进制造业'
     '“要地、要路、要集聚”的要求；①②④的位置与所给理由对不上。', 5.8),
    (13, TJ13, '', '', '自然带与生态',
     '红树林在蓝碳生态系统中发挥的作用是（　　）',
     ['维持海岸稳定', '增加海洋碳汇', '培育渔业资源', '提供旅游景观'], 1,
     '题干限“在蓝碳生态系统中”，蓝碳指海洋生物固定的碳，红树林的作用就是增加海洋碳汇；'
     '护岸、育渔、观光都不属于“碳”的范畴。', 5.2),
]

# ---------------------------------------------------------------- 甘肃
GS_MAT = ('下表为我国三个城市 2024 年 12 月某日的日出日落时刻（北京时间）。'
          '据此完成下面小题。\n'
          '[[table]]\n'
          '城市|日出时刻|日落时刻\n'
          '甲|07:06|16:48\n'
          '乙|07:57|18:07\n'
          '丙|08:12|17:54\n'
          '[[/table]]')

GS = [
    (9, GS_MAT, '', '', '地球运动',
     '纬度相同的城市是（　　）',
     ['甲和乙', '甲和丙', '乙和丙', '甲乙丙'], 1,
     '同纬度同日昼长相等。甲 16:48−07:06＝9h42m，丙 17:54−08:12＝9h42m，乙为 10h10m，'
     '所以甲、丙同纬度。', 5.4),
    (10, GS_MAT, '', '', '地球运动',
     '乙、丙两城市日出时刻（北京时间）相同时（　　）',
     ['北极圈以北全部出现极夜', '甲城市太阳高度全年最大',
      '乙城市日出正东日落正西', '丙城市白昼长度全年最长'], 2,
     '两地日出时刻相同，说明经度差恰好抵消了纬度差带来的时差，此日为二分日；'
     '二分日全球（极点除外）日出正东、日落正西。', 6.2),
]

# ---------------------------------------------------------------- 江西 8—10
# 原卷这一组材料后附「M 集团全球化投资与生产布局表」，但 gaokao.cn 这份 PDF 转档时把表丢了
# （文字层里只剩「下表示意……据此完成下面小题」，表体没有）。三道小题本身不依赖表内具体数字，
# 故按原题补入，材料末尾注明原卷附表，避免让人以为题干少了一段。
JX_MAT = ('总部位于甘肃金昌的 M 集团是集有色金属开采、冶炼、加工为一体的国有企业。20 世纪 80 年代，'
          '该企业开始海外投资与生产，逐步成为中国西部规模最大的资源型企业之一。近年来，'
          'M 集团在广西防城港建成大型加工中心。下表示意 M 集团的全球化投资与生产布局情况'
          '（原卷此处附有投资与生产布局表）。据此完成下面小题。')

JX = [
    (8, 'M 集团进行海外投资与生产的主要目的是（　　）',
     ['降低生产成本', '获取生产原料', '提高生产技术', '拓展海外市场'], 1,
     'M 集团干的是有色金属“开采—冶炼—加工”，海外布点首先是为了拿到矿——原料指向，'
     '不是市场或技术。', 5.4),
    (9, 'M 集团将开采环节分散在全球多个国家，主要考虑的是（　　）',
     ['产品规模', '运输成本', '原料品质', '资源安全'], 3,
     '把开采分散到多国，是避免单一来源断供，属于资源安全（供应安全）考量。', 5.8),
    (10, '与金昌相比，防城港作为 M 集团加工中心所在地的优势是（　　）',
     ['技术', '政策', '交通', '劳动力'], 2,
     '防城港是北部湾港口，进口矿石可海运直达，加工后也便于外运——核心优势是交通。', 5.2),
]



def save_fig(src, name):
    im = Image.open(src).convert('RGB')
    if im.width > 1200:
        im = im.resize((1200, round(im.height * 1200 / im.width)), Image.LANCZOS)
    p = os.path.join(FIG, name)
    im.save(p, 'WEBP', quality=88, method=6)
    return p, im.size


def main():
    items = []

    tj_fig = save_fig(os.path.join(SRC_TJ, 't89.png'), 'tj2025-11.webp')
    for no, mat, fig, figalt, theme, q, opts, ans, exp, diff in TJ:
        it = {
            'id': 'tj2025-%d' % no, 'type': 'choice',
            'lv': 'sr', 'grade': '高中', 'band': '高中',
            'exam': 'gk', 'year': YEAR, 'paper': '天津卷', 'no': no,
            'prov': '天津', 'city': '',
            'theme': theme, 'cat': '真题',
            'tags': ['真题', '2025', '天津卷', theme],
            'diff': diff, 'score': diff, 'point': 3,
            'material': mat, 'q': q, 'opts': opts, 'ans': ans,
            'ansText': '', 'exp': exp, 'card': '', 'cardName': '',
            'src': '2025 天津卷 · 第 %d 题' % no,
            'figure': '', 'figureAlt': '', 'figW': 0, 'figH': 0,
        }
        if fig:
            it['figure'] = tj_fig[0].replace(os.sep, '/')
            it['figureAlt'] = figalt
            it['figW'], it['figH'] = tj_fig[1]
        items.append(it)

    for no, mat, fig, figalt, theme, q, opts, ans, exp, diff in GS:
        items.append({
            'id': 'gs2025-%d' % no, 'type': 'choice',
            'lv': 'sr', 'grade': '高中', 'band': '高中',
            'exam': 'gk', 'year': YEAR, 'paper': '甘肃卷', 'no': no,
            'prov': '甘肃', 'city': '',
            'theme': theme, 'cat': '真题',
            'tags': ['真题', '2025', '甘肃卷', theme],
            'diff': diff, 'score': diff, 'point': 3,
            'material': mat, 'q': q, 'opts': opts, 'ans': ans,
            'ansText': '', 'exp': exp, 'card': '', 'cardName': '',
            'src': '2025 甘肃卷 · 第 %d 题' % no,
            'figure': '', 'figureAlt': '', 'figW': 0, 'figH': 0,
        })

    for no, q, opts, ans, exp, diff in JX:
        items.append({
            'id': 'jx2025-c%d' % no, 'type': 'choice',
            'lv': 'sr', 'grade': '高中', 'band': '高中',
            'exam': 'gk', 'year': YEAR, 'paper': '江西卷', 'no': no,
            'prov': '江西', 'city': '',
            'theme': '产业与区域', 'cat': '真题',
            'tags': ['真题', '2025', '江西卷', '产业与区域'],
            'diff': diff, 'score': diff, 'point': 3,
            'material': JX_MAT, 'q': q, 'opts': opts, 'ans': ans,
            'ansText': '', 'exp': exp, 'card': '', 'cardName': '',
            'src': '2025 江西卷 · 第 %d 题' % no,
            'figure': '', 'figureAlt': '', 'figW': 0, 'figH': 0,
        })

    d = json.load(io.open(BANK, encoding='utf-8'))
    byid = {i['id']: i for i in d['items']}
    add = [i for i in items if i['id'] not in byid]
    for i in items:
        if i['id'] in byid:
            byid[i['id']].update(i)
    d['items'].extend(add)
    d['ver'] = '2026-11-28-real-23'
    io.open(BANK, 'w', encoding='utf-8', newline='').write(
        json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    print('补漏 %d 题，题库 %d 条' % (len(add), len(d['items'])))


if __name__ == '__main__':
    main()
