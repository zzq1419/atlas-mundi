# -*- coding: utf-8 -*-
"""对扫描版试卷逐页做 OCR，输出带坐标的 JSON（供后续裁图和录入用）。

用法：python scripts/ocr_pdf.py <渲染图目录> <输出目录> <起始页> <结束页>
"""
import io
import json
import os
import sys

from rapidocr_onnxruntime import RapidOCR


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else '_fj'
    out = sys.argv[2] if len(sys.argv) > 2 else '_fj_ocr'
    a = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    bpage = int(sys.argv[4]) if len(sys.argv) > 4 else 99
    os.makedirs(out, exist_ok=True)

    engine = RapidOCR()
    files = sorted(f for f in os.listdir(src) if f.lower().endswith('.png'))
    for f in files:
        idx = int(''.join(ch for ch in f if ch.isdigit()))
        if idx < a or idx > bpage:
            continue
        res, _ = engine(os.path.join(src, f))
        rows = []
        if res:
            for box, text, score in res:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                rows.append({
                    'text': text,
                    'x': round(min(xs)), 'y': round(min(ys)),
                    'w': round(max(xs) - min(xs)), 'h': round(max(ys) - min(ys)),
                    'score': round(float(score), 3)
                })
            rows.sort(key=lambda r: (r['y'], r['x']))
        with io.open(os.path.join(out, f.replace('.png', '.json')), 'w',
                     encoding='utf-8') as fp:
            json.dump(rows, fp, ensure_ascii=False, indent=0)
        lines = len(rows)
        print('%s  %d 行' % (f, lines))
        # 顺带打印成文本，方便直接读
        with io.open(os.path.join(out, f.replace('.png', '.txt')), 'w',
                     encoding='utf-8') as fp:
            last = None
            for r in rows:
                if last is not None and r['y'] - last > 10:
                    fp.write('\n')
                fp.write(r['text'])
                last = r['y']
            fp.write('\n')


if __name__ == '__main__':
    main()
