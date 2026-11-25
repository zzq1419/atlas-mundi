# -*- coding: utf-8 -*-
"""下载高考地理真题原始数据到 _real/（不入库）。

数据来源：
  · OpenLMLab/GAOKAO-Bench            2010—2022 地理选择题 + 简答题（带解析）
  · OpenLMLab/GAOKAO-Bench-Updates    2023、2024 地理选择题
  · FairyWorld/ai_chinese-llm-benchmark  2025 各省地理选择题（纯文本客观题）

后两个只作补充：Updates 里地理只有 6 组、2025 那批 19 道且没有解析，
主力是 GAOKAO-Bench 的 34 组。

用法：python scripts/bank/fetch.py
再用：python scripts/bank/parse.py && python scripts/bank/tag.py && python scripts/bank/build.py
"""
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, '_real')

BASE_GK = 'https://raw.githubusercontent.com/OpenLMLab/GAOKAO-Bench/main/'
BASE_UP = 'https://raw.githubusercontent.com/OpenLMLab/GAOKAO-Bench-Updates/main/'
BASE_FW = ('https://raw.githubusercontent.com/FairyWorld/ai_chinese-llm-benchmark/main/'
           'opendata/2025%E9%AB%98%E8%80%83%E5%90%84%E7%9C%81%E7%9C%9F%E9%A2%98/')

FILES = [
    (BASE_GK + 'Data/Objective_Questions/2010-2022_Geography_MCQs.json', 'gk_obj.json'),
    (BASE_GK + 'Data/Subjective_Questions/2010-2022_Geography_Open-ended_Questions.json', 'gk_sub.json'),
    (BASE_UP + 'Data/GAOKAO-Bench-2023/2023_Geography_MCQs.json', 'gk_2023.json'),
    (BASE_UP + 'Data/GAOKAO-Bench-2024/2024_Geography_MCQs.json', 'gk_2024.json'),
    (BASE_FW + '2025%E9%AB%98%E8%80%83%E5%9C%B0%E7%90%86-v20250623.json', '2025.json'),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for url, name in FILES:
        dst = os.path.join(OUT, name)
        if os.path.exists(dst) and os.path.getsize(dst) > 1000:
            print('已存在', name, os.path.getsize(dst), 'B')
            continue
        req = urllib.request.Request(url, headers={'User-Agent': 'atlas-mundi/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
        except Exception as e:
            print('失败', name, e)
            continue
        open(dst, 'wb').write(data)
        print('下载', name, len(data), 'B')


if __name__ == '__main__':
    main()
