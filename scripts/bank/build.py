# -*- coding: utf-8 -*-
"""把 tagged.json 落成前端要的 assets/bank/real.json，schema 与 geo.json 对齐。"""
import json
import os
import re
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    items = json.load(open(os.path.join(ROOT, '_real/tagged.json'), encoding='utf-8'))
    out = []
    for it in items:
        tags = ['真题', it['year'], it['paper']]
        if it['cardName']:
            tags.append(it['cardName'])
        out.append({
            'id': it['id'],
            'type': 'choice',
            'lv': 'sr',
            'grade': '高中',
            'band': '高中',
            'theme': it['theme'],
            'cat': '真题',
            'tags': tags,
            'diff': it['diff'],
            'q': it['q'],
            'opts': it['opts'],
            'ans': it['ans'],
            'exp': it['exp'],
            'ansText': '',
            'card': it['card'],
            'cardName': it['cardName'],
            'src': it['src'],
            # score 在前端是“掌握分”（0–10 的区间筛选用它），不是卷面分值；
            # 卷面分另存 point，免得 4 分的选择题被当成“掌握分 4”排到最简单那一档。
            'score': it['diff'],
            'point': it['score'],
            'material': it['material'],
            'year': it['year'],
            'paper': it['paper'],
            'no': it['no'],
        })

    # 按年份倒序 + 卷别 + 题号，界面上看起来像一份份卷子
    out.sort(key=lambda x: (x['year'], x['paper'], x['no']), reverse=True)
    doc = {
        'ver': '2026-11-25-real-1',
        'note': '高考地理真题（2011—2024），材料为共用题组材料，每题自带年份与卷别',
        'items': out,
    }
    p = os.path.join(ROOT, 'assets/bank/real.json')
    json.dump(doc, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('写入', p, len(out), '题', round(os.path.getsize(p) / 1024, 1), 'KB')
    print('年份', collections.Counter(x['year'] for x in out).most_common())
    print('难度', collections.Counter(x['diff'] for x in out).most_common(8))


if __name__ == '__main__':
    main()
