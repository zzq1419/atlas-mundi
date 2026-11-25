# -*- coding: utf-8 -*-
"""把 GAOKAO-Bench 系的地理真题拆成单题。

源格式两套：
  A) 2010-2022：'1．（4 分）题干（ ） A．选项 B．选项 ...'（题号带分值）
  B) 2023-2024：'1. 题干（   ）\\nA. 选项\\tB. 选项'
两者都是「一段材料 + 若干小题」，answer 是数组、analysis 按题分段。

输出 _real/parsed.json：[{year,paper,no,material,q,opts,ans,exp}]
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL = os.path.join(ROOT, '_real')

SOURCES = [
    ('gk_obj.json', '2010-2022'),
    ('gk_2023.json', '2023'),
    ('gk_2024.json', '2024'),
]

# 题号不一定在行首：有的源把整段压成一行，前面的句号/空格才是边界。
# 形式有「1．（4 分）」「1.」「9．」，统一成一个宽松正则，靠"题号连续 + 个数等于答案数"收口。
RE_ITEM = re.compile(r'(\d{1,2})\s*[．.]\s*(?:[（(]\s*\d{1,2}\s*分\s*[）)])?\s*')
RE_OPT = re.compile(r'([ABCD])\s*[．.、]\s*')


def tidy(s):
    """清 OCR 噪声：全角句点、硬折行、多余空白。"""
    if not s:
        return ''
    s = s.replace('\r', '')
    s = s.replace('．', '。')
    s = s.replace('\u3000', ' ')
    # 括号里的换行要先吃掉，否则会留下 “（ \\n ）” 这种空腔
    s = re.sub(r'[（(]\s*\n\s*([）)])', '（ ）', s)
    s = re.sub(r'[（(][ \t]*\n[ \t]*', '（', s)
    s = re.sub(r'[ \t]*\n[ \t]*[）)]', '）', s)
    # 硬折行：只有上一行以句末标点收尾才算换段，其余都是排版断行，直接接上
    lines = [ln.strip() for ln in s.split('\n')]
    out = []
    for ln in lines:
        if not ln:
            continue
        if out and not out[-1].endswith(('。', '！', '？')):
            out[-1] += ln
        else:
            out.append(ln)
    s = '\n'.join(out)
    s = re.sub(r'[ \t]{2,}', ' ', s)
    return s.strip()


def split_opts(blk):
    """从一段文字里切出选项。返回 (题干, [选项...])。"""
    hits = list(RE_OPT.finditer(blk))
    # 至少要 A 开头、且依次出现才认
    if not hits or hits[0].group(1) != 'A':
        return blk.strip(), []
    seq = []
    for m in hits:
        if not seq or ord(m.group(1)) == ord(seq[-1][0]) + 1:
            seq.append((m.group(1), m.start(), m.end()))
    if len(seq) < 4 and len(hits) >= 4:
        # 源数据把选项字母写错（见过 A B C B），按出现次序当 ABCD 用
        seq = [(L, m.start(), m.end()) for L, m in zip('ABCD', hits[:4])]
    if len(seq) < 3:
        return blk.strip(), []
    stem = blk[:seq[0][1]].strip()
    opts = []
    for i, (L, a, b) in enumerate(seq):
        end = seq[i + 1][1] if i + 1 < len(seq) else len(blk)
        opts.append(blk[b:end].strip(' 。．\n\t'))
    return stem, opts


def split_items(question, n_ans):
    """把「材料 + 若干小题」切成 (材料, [(题号, 小题原文)...])。

    题号没有可靠的行首锚点（有的源整段一行、还夹着年份数字），
    所以先收所有"数字+点、后面紧跟汉字"的候选，再找长度对得上答案数的递增链。
    """
    cands = []
    for m in RE_ITEM.finditer(question):
        n = int(m.group(1))
        if n > 30:
            continue
        nxt = question[m.end():m.end() + 1]
        ok = False
        if nxt:
            if '\u4e00' <= nxt <= '\u9fa5':
                ok = True                      # 正常：题号后直接是汉字
            elif nxt in '①②③④（(“"「『【':
                ok = True                      # 题号后接序号或引号
            elif nxt.isascii() and nxt.isalpha():
                ok = True                      # “2．K 企业…” 这种
            elif nxt.isdigit():
                # 数字要当心：表格里的 “30．3” 是小数，不是题号。
                # 只有后面跟着 4 位年份才算题号（“1．2010～2020 年…”）。
                ok = bool(re.match(r'\d{4}', question[m.end():m.end() + 4]))
        if not ok:
            continue
        if m.start() > 0 and question[m.start() - 1].isdigit():
            continue                      # “2019．”这类年份
        if m.start() > 0 and question[m.start() - 1] in '（(':
            continue                      # “（3 分）”里的分值是上一处
        cands.append((n, m.start(), m.end()))

    best, best_score = None, -1
    for i in range(len(cands)):
        chain = [cands[i]]
        for c in cands[i + 1:]:
            if c[0] == chain[-1][0] + 1:
                chain.append(c)
            elif c[0] > chain[-1][0] + 1:
                break
        # 长度命中答案数的优先，其次取最长
        score = (1000 if len(chain) == n_ans else 0) + len(chain)
        if score > best_score:
            best, best_score = chain, score
        if len(chain) == n_ans:
            break
    if not best:
        return tidy(question), []
    material = question[:best[0][1]]
    items = []
    for i, (n, a, b) in enumerate(best):
        end = best[i + 1][1] if i + 1 < len(best) else len(question)
        items.append((n, question[b:end]))
    return tidy(material), items


def _cut(marks, text, nums):
    """按给定的切点把 text 切段，并核验题号序列。"""
    out = []
    for i, (no, a, b) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out.append(text[b:end].strip())
    if [m[0] for m in marks] == list(nums):
        return out
    return None


def split_exp(analysis, nums):
    """把解析按题拆开。

    这套语料里解析有三种写法，按可靠性从高到低试：
      B) '9.【解答】解：…'      —— 带题号，最可靠
      A) '【3题详解】…'          —— 2023 起的新写法
      C) 纯 '解：…故选：X。'     —— 无题号，靠个数对上
      D) 只在 '故选：X' 处切     —— 有的解析连句号都没有（'故选：B'）
    """
    a = tidy(analysis or '')
    n = len(nums)
    if n <= 1:
        return [a]

    marks = [(int(m.group(1)), m.start(), m.end()) for m in
             re.finditer(r'(\d{1,2})\s*[．.、]?\s*【\s*(?:解答|分析|详解|解析)\s*】', a)]
    if len(marks) == n:
        r = _cut(marks, a, nums)
        if r:
            return r

    # 2023 起的写法更残缺：【3详解】少了「题」、「7题详解】」缺左括号。
    # 先补成统一形态，再按题号切。
    b = re.sub(r'(?<![【\[])(\d{1,2})\s*题?[^】\]]{0,4}[】\]]', r'【\1题详解】', a)
    b = re.sub(r'【\s*(\d{1,2})\s*题?[^】\]]{0,4}[】\]]', r'【\1题详解】', b)
    marks = [(int(m.group(1)), m.start(), m.end()) for m in
             re.finditer(r'【\s*(\d{1,2})\s*题[^】]*】', b)]
    if len(marks) == n:
        r = _cut(marks, b, nums)
        if r:
            return r

    parts = [p.strip() for p in re.split(r'(?=解\s*[：:])', a) if p.strip()]
    # 首段常常只是被剥下来的 '6.【解答】' 残渣
    if len(parts) == n + 1 and len(parts[0]) < 16:
        parts = parts[1:]
    if len(parts) == n and all(parts):
        return parts

    cuts = [m.end() for m in re.finditer(r'故选\s*[：:]?\s*[ABCD]', a)]
    if len(cuts) == n:
        parts, prev = [], 0
        for k in cuts:
            parts.append(a[prev:k].strip(' 。'))
            prev = k
        if all(parts):
            return parts

    return [a] + [''] * (n - 1)


def main():
    out = []
    stat = {}
    for fn, label in SOURCES:
        path = os.path.join(REAL, fn)
        if not os.path.exists(path):
            continue
        d = json.load(open(path, encoding='utf-8'))
        ex = d['example'] if isinstance(d, dict) else d
        for e in ex:
            q = e['question']
            ans = e.get('answer') or []
            if not isinstance(ans, list):
                ans = [ans]
            material, items = split_items(q, len(ans))
            if not items:
                continue
            # 题号顺序应与答案个数对得上；对不上就整组丢弃（宁可少收不可错配）
            if len(items) != len(ans):
                stat.setdefault('skip_mismatch', []).append(
                    (label, e.get('year'), e.get('category'), len(items), len(ans)))
                continue
            exps = split_exp(e.get('analysis'), [n for n, _ in items])
            for i, (no, body) in enumerate(items):
                stem, opts = split_opts(body)
                if len(opts) != 4:
                    stat.setdefault('skip_opts', []).append(
                        (label, e.get('year'), no, len(opts), body[:60]))
                    continue
                a = str(ans[i]).strip().upper()[:1]
                if a not in 'ABCD':
                    stat.setdefault('skip_ans', []).append((label, no, ans[i]))
                    continue
                out.append(dict(
                    year=str(e.get('year') or label),
                    paper=(e.get('category') or '').strip('（）() '),
                    no=no,
                    score=e.get('score') if len(items) == 1 else None,
                    material=material,
                    q=tidy(stem),
                    opts=[tidy(o) for o in opts],
                    ans='ABCD'.index(a),
                    exp=tidy(exps[i] if i < len(exps) else ''),
                ))
    json.dump(out, open(os.path.join(REAL, 'parsed.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('题数', len(out))
    for k, v in stat.items():
        print(k, len(v))
        for row in v[:4]:
            print('   ', row)


if __name__ == '__main__':
    main()
