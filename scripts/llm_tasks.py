#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""六类大模型任务的具体实现（构建期跑，产物落 JSON）。

对应课程评分表「使用大模型做特征提取与融合、构建知识库」，拆成六类：

| # | 函数 | 用途 | 解决什么真问题 |
|---|------|------|----------------|
| 1 | disambiguate      | 实体消歧 | 中文译名撞车（圣米歇尔山 → 摩泽尔省教堂） |
| 2 | extract_facets    | 特征抽取 | 节庆/饮食/宗教这类语义特征，规则抽不出 |
| 3 | refine_summary    | 摘要精炼 | Wikipedia extracts 机截断，可能断在半句 |
| 4 | translate_caption | 图注翻译 | Commons 的 caption 是英文，250 国不可能手写 |
| 5 | audit_record      | 数据质检 | CI 只查格式，查不出「首都写错」这类语义错 |
| 6 | answer_query      | 检索问答 | 前端搜索框与知识库的落地 |

设计约定
--------
- 每个函数只做一件事：输入纯数据、输出纯数据，不读写文件，方便单测。
- 失败时抛 LLMError，不返回半成品 —— 空串写进 JSON 是最难查的错。
- 所有调用默认关闭 thinking（见 llm.py 的说明），只有需要权衡多候选时才开。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# 控制台可能是 cp936（Windows cmd 默认），打不出的字符用 ? 代替，别让整段崩掉。
# 之前 collect.py 在连不上某个站时打印一个 ✗ 就 UnicodeEncodeError 退出，
# 看起来像"采集失败"，其实连抓取都还没开始。
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm import LLMError, chat, chat_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREVIEW = os.path.join(ROOT, "data", "_llm")


# ---------------------------------------------------------------- 1 实体消歧
DISAMBIGUATE_SYSTEM = (
    "你是 Wikidata 实体消歧助手。中文译名与欧洲小地名撞车是常态，"
    "你要根据描述、行政层级、地理坐标判断哪个条目是用户真正要找的对象。"
    "宁可返回 null 也不要选一个明显不对的候选。"
)


def disambiguate(target: dict, candidates: list[dict], thinking: bool = False) -> dict:
    """从若干同名/近名候选里挑出目标实体。

    target: {"zh": "圣米歇尔山", "en": "Mont Saint-Michel",
             "type": "地标（潮汐岛与修道院）", "country": "法国"}
    candidates: [{"qid","label","desc","country","coord"}...]

    返回 {"pick": qid|None, "confidence": float, "reason": str, "reject": [...]}
    """
    if not candidates:
        return {"pick": None, "confidence": 0.0, "reason": "无候选", "reject": []}

    listing = json.dumps(candidates, ensure_ascii=False, indent=2)
    prompt = f"""我们要定位的对象：
- 中文名：{target.get('zh')}
- 英文名：{target.get('en') or '（未知）'}
- 类型：{target.get('type') or '（未知）'}
- 已知所属：{target.get('country') or '（未知）'}

候选条目（来自 Wikidata 搜索，可能混入同名但不同的东西）：
{listing}

判断哪个候选才符合上述对象。注意：
1. 不要仅因 label 相同就选 —— 要看 desc 里的行政层级（市镇 commune / 人类聚居地
   与地标 landmark 是两类东西）。
2. 坐标可用于辅助判断，但不要假设纬度经度顺序，只有明显矛盾时才据此排除。
3. 若全部明显不符，pick 返回 null。

只输出 json，格式：
{{"pick": "选中的 qid 或 null", "confidence": 0.0到1.0的小数,
  "reason": "不超过 50 字，说明依据",
  "reject": [{{"qid": "被排除的 qid", "why": "不超过 20 字"}}]}}"""

    d = chat_json(prompt, system=DISAMBIGUATE_SYSTEM, scene="disambiguate",
                  thinking=thinking, max_tokens=900,
                  note=target.get("zh") or "")

    pick = d.get("pick")
    if isinstance(pick, str) and pick.strip().lower() in ("null", "none", ""):
        pick = None
    qids = {c.get("qid") for c in candidates}
    if pick not in qids:
        # 模型可能返回了 label，或者瞎编了一个 qid —— 一律当没选
        pick = None

    reject = []
    for r in (d.get("reject") or []):
        if isinstance(r, dict):
            reject.append({"qid": r.get("qid"), "why": str(r.get("why") or "")[:40]})
        elif isinstance(r, str):
            reject.append({"qid": None, "why": r[:40]})

    try:
        conf = float(d.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if pick is None:
        conf = 0.0

    return {"pick": pick, "confidence": round(conf, 2),
            "reason": str(d.get("reason") or "")[:120], "reject": reject}


# ---------------------------------------------------------------- 2 特征抽取
FACETS_SYSTEM = (
    "你是文化地理数据标注员。你只从给定文本里抽取明说的信息，"
    "绝不补充文本没有的内容。抽不到就返回空数组，不要编造。"
)


def extract_facets(record: dict) -> dict:
    """从摘要与民俗文本里抽取结构化文化特征。

    这是评分表原话「特征提取」的落地：把非结构化文本变成可比对的标签，
    这样 250 国之后才能做「相似国家推荐」「按节庆检索」这类功能。
    每个标签都带 evidence（原文片段），便于人工核查，避免模型凭空发挥。
    """
    text = "\n\n".join(x for x in [(record.get("summary_text") or ""),
                                   (record.get("custom_text") or "")] if x)
    if not text.strip():
        return {"festivals": [], "cuisine": [], "religion": [], "architecture": [],
                "heritage": [], "keywords": [], "note": "无文本可抽"}

    prompt = f"""下面是关于「{record.get('name_zh')}」的文本。请抽取结构化特征。

文本：
{text}

各字段定义与要求：
- festivals：明确提到的节庆、纪念日
- cuisine：明确提到的饮食、食材或饮食制度（如「AOP 原产地制度」「面包与葡萄酒」）
- religion：明确提到的宗教，或宗教与世俗关系的制度
- architecture：明确提到的建筑类型、聚落形制或建筑风格
- heritage：明确提到的世界遗产、文物保护对象
- keywords：3~6 个最能代表该条目**文化意象**的词。
  优先取：地貌地标、物产饮食、传统节庆、艺术与建筑、语言与方言。
  **禁止**：该国自身名称、行政区划的数量（如「18 个大区」）、
  政治制度与政治事件、历史族群名、纯数字。
  正例：中国 → 长城、兵马俑、春节、三级阶梯、粤语
  反例：法国本身、18 个大区、双首长制、高卢人

每条必须是 {{"v": "词", "evidence": "原文中的片段，不超过 20 字"}}。
原文没提的类别返回空数组 []。不要推测。

只输出 json。"""
    d = chat_json(prompt, system=FACETS_SYSTEM, scene="extract_facets",
                  max_tokens=1600, note=record.get("name_zh") or "")

    out = {}
    for k in ("festivals", "cuisine", "religion", "architecture", "heritage", "keywords"):
        items = []
        for it in (d.get(k) or []):
            if isinstance(it, dict) and it.get("v"):
                items.append({"v": str(it["v"])[:24],
                              "evidence": str(it.get("evidence") or "")[:40]})
            elif isinstance(it, str) and it.strip():
                items.append({"v": it.strip()[:24], "evidence": ""})
        out[k] = items[:8]
    out["model"] = "deepseek-flash"
    return out


# ---------------------------------------------------------------- 3 摘要精炼
SUMMARY_SYSTEM = (
    "你是中文百科编辑。你只做删减与重组，不引入原文没有的事实。"
    "句子必须完整，不能在句中截断。"
)


def refine_summary(record: dict, target_min: int = 240, target_max: int = 420) -> dict:
    """把摘要改写成 240~420 字的地理文化段落。

    三个动机：
    1. 采集时是从 Wikipedia extracts 按字数硬切的，末尾可能断在半句。
    2. **统一口径**：本项目是「多模态文化图谱」，国家简介应当只讲地理与文化。
       Wikipedia 导语常以政权更迭、战争、政治制度开篇，各国内容量差异极大，
       既不利于横向比较，也会让不同国家条目风格割裂。
    3. 单靠百科导语，剔掉政治史后往往不足 300 字（中国实测只剩 188 字），
       所以把人工撰写的 custom_text 一并作为素材，篇幅才撑得住。
    """
    a = (record.get("summary_text") or "").strip()
    b = (record.get("custom_text") or "").strip()
    if not (a or b):
        raise LLMError("无素材可写")

    raw = a
    prompt = f"""请为「{record.get('name_zh')}」写一段 {target_min}~{target_max} 字的中文简介。

素材 A（百科导语）：
{a or "（无）"}

素材 B（文化民俗）：
{b or "（无）"}

围绕四个主题，按此顺序组织：
1. 地理区位：位于哪个洲、濒临什么海或洋、与哪些国家接壤、国土面积
2. 自然与地形：主要山脉、河流、地形起伏
3. 行政区划：省级行政区划分、首都
4. 语言与文化：通用语言与主要方言、宗教与世俗制度、饮食特色、传统节庆、世界遗产

规则（严格遵守）：
- 只使用素材 A、B 中已有的信息，不新增任何事实或数字。
- 某个主题在两段素材里都没有内容时，**直接跳过该主题**，
  不许写「暂无内容」「未提及」「素材中没有」这类元话语。
- 不写战争过程、政权更迭细节、政党与政治制度、外交或领土争议。
  文化制度层面的表述（如政教分离原则 laïcité、共和传统）属于文化，可以保留。
- 结尾必须是完整句子，不能在列举中断掉。
- 简体中文，客观第三人称，不用「我国」。
- 直接输出正文，不要标题、不要 markdown、不要分段标题。

只输出 json，键为 text。"""
    d = chat_json(prompt, system=SUMMARY_SYSTEM, scene="refine_summary",
                  max_tokens=1400, note=record.get("name_zh") or "")
    text = (d.get("text") or "").strip()
    if not text:
        raise LLMError("模型返回空摘要")
    return {"text": text, "chars": len(text), "raw_chars": len(raw),
            "raw_tail": raw[-30:], "new_tail": text[-30:]}


# ---------------------------------------------------------------- 4 图注翻译
CAPTION_SYSTEM = (
    "你是中英专有名词翻译。地名、建筑名使用中国大陆通行译名。"
    "只输出译名本身，不加引号、不加解释。"
)


def translate_caption(en_source: str, landmark_zh: str = "") -> str:
    """从 Commons 英文文件名生成中文图注。

    为什么要用文件名而不是 ImageDescription：Commons 的 ``ImageDescription``
    经常是空的或只有一句拍摄备注，而**文件名几乎总是由上传者按主体命名**，
    包含主体、视角、地点三类信息（``Statue of Liberty and a sightseeing boat,
    Liberty Island, New York`` ／ ``WhiteHouseSouthFacade`` ／
    ``Ceiling of Hall of Mirrors (Palace of Versailles)``）。

    对 250 国来说这条是刚需：每国 2~4 张图，人工写 1000 条图注不现实。
    当前 3 国已人工写过，这里重跑是为了验证「模型产出能否达到人工水准」，
    产出存 caption_llm_zh 与原 caption_zh 并存，可逐条比对。
    """
    src = (en_source or "").strip()
    if not src:
        return landmark_zh

    prompt = (f"下面是一个 Wikimedia Commons 文件名，描述一张关于「{landmark_zh}」的照片。\n"
              f"文件名：{src}\n\n"
              f"请生成中文图注，8~20 字，要求：\n"
              f"1. 必须含「{landmark_zh}」这个主体名\n"
              f"2. 文件名里若有视角或局部信息（如 facade / ceiling / courtyard / "
              f"at night / from the air / pit 1），要体现出来\n"
              f"3. 文件名里没有的信息一律不要加，不要编造地理位置或年代\n"
              f"4. 不要写「一张…的照片」这种废话\n"
              f"5. 不要加「景观」「风光」「景色」「风景」「风貌」这类空泛后缀 —— "
              f"它们不传递任何信息。文件名没有额外信息时，直接用主体名即可\n\n"
              f"只输出 json，键为 zh。")
    d = chat_json(prompt, system=CAPTION_SYSTEM, scene="translate_caption",
                  max_tokens=200, note=landmark_zh)
    out = (d.get("zh") or "").strip().strip('"“”')
    return out[:40] or landmark_zh


# ---------------------------------------------------------------- 7 民俗成文
# 每国分一个切入角度。不这么做的话，模型会把 prompt 里的示例当成模板 ——
# 实测给了一句"清早面包房刚开门"，巴西、挪威、埃及、不丹四国全拿这句话开头，
# 只是把面包换成豆蔻卷或大饼。角度按国名哈希定，同一国每次都一样（可复现）。
# 场景锚点：prompt 里强制"第一句只写这一个场景"。
# 试过两轮黑名单（"XX人过日子" → 又变成"天还没亮+面包房"），
# 禁一个它换一个，埃及和德国前 13 个字能做到完全一样。
# 正面指定一个锚点才管用 —— 每个国家按 ISO 稳定抽一个，互不重复。
# 开头黑名单。prompt 里写了两轮"禁止用时间状语开场"都没用 ——
# 实测四个国家（巴西/不丹/德国/埃及）连着写出"天还没亮透，街角面包房……"。
# 模型对"民俗"的强先验压过了文字约束，只能生成后检测、不合格就重写。
BAN_HEAD = ("天还没亮", "天未亮", "天刚亮", "拂晓", "清早", "清晨", "早晨",
            "早上", "一早", "早饭", "早餐", "早点", "面包房", "面包店", "早市")

ANCHORS = (
    "菜市场里怎么讨价还价",
    "孩子第一天上学",
    "婚礼上谁先动筷、谁坐哪",
    "葬礼上穿什么、怎么办",
    "一双手正在做的那件活",
    "屋里的灶或炉子",
    "雨或雪落下来的那一天",
    "邻居之间怎么送东西",
    "长辈怎么称呼晚辈",
    "坐公交或渡船的时候",
    "理发、修面、整衣冠",
    "一年里最热的那几天",
    "收割或出海的那几天",
    "往庙里或教堂走的路上",
    "吃完晚饭以后做什么",
    "家里谁做主、怎么分活儿",
    "门口或院子里的那点事",
    "穿衣打扮上的一件讲究",
    "生病了怎么办",
    "过节前怎么准备",
)

COMPOSE_SYSTEM = (
    "你是民俗写作者。你写的是\u201c那里的人怎么过日子\u201d，不是国家概况。\n"
    "你熟悉世界各地的节庆、饮食与传统习俗，可以写材料之外广为人知的民俗常识；\n"
    "但凡涉及年份、人数、面积、产量、排名这类可被证伪的数字，一律不写。\n"
    "判断标准：一句话如果换个国家也成立（\u201c位于欧洲西部\u201d\u201c人口约八千万\u201d），"
    "它就属于概况，不属于民俗，不要写。"
)


def compose_history(record: dict) -> dict:
    """把维基导语与已抽特征写成「历史与民俗」一段（250~350 字中文）。

    中法美三国这一段是人工撰写的；要覆盖 200 多个国家，只能让模型写。
    风险是编造，所以 prompt 里把"只用给定材料"写成硬约束，
    并且产出会连同 evidence 一起存进 data/_llm/ 供人工抽查。
    """
    summary = (record.get("summary_text") or "").strip()
    if not summary:
        raise LLMError("没有摘要文本，无法成文（先跑采集）")

    facets = record.get("custom_facets") or {}
    fl = []
    for k, label in (("festivals", "节庆"), ("cuisine", "饮食"), ("religion", "宗教"),
                     ("architecture", "建筑"), ("heritage", "遗产")):
        vals = [x.get("v") if isinstance(x, dict) else x for x in (facets.get(k) or [])]
        vals = [v for v in vals if v]
        if vals:
            fl.append("%s：%s" % (label, "、".join(vals[:6])))
    facet_txt = "\n".join(fl) or "（无）"

    # 按 ISO 稳定抽一个场景锚点：同一国每次一致（可复现），不同国错开
    import hashlib
    _key = str(record.get('iso_a2') or record.get('name_zh') or '')
    _h = int(hashlib.md5(_key.encode()).hexdigest()[:8], 16)
    anchor = ANCHORS[_h % len(ANCHORS)]

    prompt = f"""国家：{record.get('name_zh')}（{record.get('name_en') or ''}）
首都：{record.get('capital') or '—'}
大洲：{record.get('continent') or '—'}

【材料一：维基导语】
{summary[:1200]}

【材料二：已抽取的文化特征】
{facet_txt}

请写一段「民俗与日常」，要求：

1. 240~340 字，纯中文，不分点、不加标题，一或两个自然段。
2. 只写这个国家的人**怎么生活**：一年里怎么过节、日常吃什么、
   待人接物有什么讲究、穿什么、做什么手艺、信什么、有哪些绕不开的仪式感。
3. **严禁写地理位置、面积、人口、政体、行政区划、经济数据**。
   这些读者在上面已经看过，再写一遍就是废话。
4. 上面【材料二】里提到的节庆/食物/习俗优先写；材料没提到的，
   可以写该国广为人知的民俗（德国就写啤酒节与面包，卢旺达就写
    Umuganura 丰收节这类），**但不许写具体年份、人数、产量、排名**。
5. 宁可短一点、具体一点，也不要为了凑字数回到国土地理上。
6. 语气像一位在当地住过一阵的人在讲见闻：具体、可感、不抒情、不总结陈词。
7. **开头不能是概括句**。具体禁止这些句式（实测模型会反复用）：
   "XX 人过日子……"、"在 XX，日子是……"、"XX 人的一天从……开始"、"XX 人离不开……"。
   也不要反复用"绕不开"这个词。
   换成从一个具体动作或场景直接切进去：清早面包房刚开门、婚礼上谁先动筷、
   雨季第一场雨落下、市场里怎么还价、孩子第一次被带去教堂。
   **第一句不要报国名**，读者从细节里认得出是哪。

自检两步：
① 有任何一句"换个国家也成立"，删掉重写；
② 把第一句单独拎出来读，如果它是"某国人如何如何"的概括，整段重写开头。

只输出 JSON：{{"text": "……"}}"""

    d = chat_json(prompt, scene="compose", max_tokens=900, system=COMPOSE_SYSTEM)
    text = str(d.get("text") or "").strip()

    # 开头检测：命中黑名单就带着"上一版哪里不合格"重写，最多两次。
    # 单次成本约 0.005 元，两次封顶，不会因为重写把账单翻上去。
    for attempt in range(2):
        head = text[:16]
        hit = next((w for w in BAN_HEAD if w in head), None)
        if not hit:
            break
        retry = prompt + (
            "\n\n【上一版不合格】你写的开头是：「%s……」\n"
            "其中「%s」是被明确禁止的模板 —— 这类开头在别的国家稿子里已经出现过多次。\n"
            "请整段重写：第一句不许出现任何时间词（清晨/早上/天还没亮/清早/拂晓），"
            "不许出现早餐、面包房、早点摊、早市；直接从「%s」这一个场景的中间切入。"
            % (head, hit, anchor))
        d = chat_json(retry, scene="compose", max_tokens=900, system=COMPOSE_SYSTEM)
        text = str(d.get("text") or "").strip()
        if len(text) < 120:
            break

    if len(text) < 120:
        raise LLMError("成文过短（%d 字），疑似材料不足" % len(text))
    return {"text": text, "chars": len(text),
            "source": "llm_compose_from_summary_facets"}


# ---------------------------------------------------------------- 5 数据质检
AUDIT_SYSTEM = (
    "你是数据质检员。你只报告能从给定字段直接判断出的矛盾，"
    "不做推测。没有问题时明确说没有。"
)


def audit_record(record: dict) -> dict:
    """语义层面的体检 —— CI 的 check_data.py 只能查格式，查不出「首都写错」。"""
    brief = {
        "name_zh": record.get("name_zh"),
        "name_en": record.get("name_en"),
        "capital": record.get("capital"),
        "continent": record.get("continent"),
        "centroid": record.get("centroid"),
        "languages": [{"code": l.get("code"), "name": l.get("name_zh"),
                       "role": l.get("role")} for l in (record.get("languages") or [])],
        "image_captions": [i.get("caption_zh") or i.get("caption")
                           for i in (record.get("landmark_images") or [])],
        "summary_head": (record.get("summary_text") or "")[:160],
    }
    prompt = f"""检查下面这条国家/地区档案有没有内部矛盾或事实错误：
{json.dumps(brief, ensure_ascii=False, indent=2)}

重点检查：
1. capital 是否确为该国的首都（注意：有些国家首都不是最大城市）
2. continent 是否与坐标大致相符
3. languages 里的语言是否确实在该国使用，role 标注是否合理
4. image_captions 的地标是否真的在该国（不要把别国的地标写进来）
5. summary_head 里的定位描述与 continent 是否一致

只报告你能确定的错误，不确定的不要报。
只输出 json：
{{"issues": [{{"field": "字段名", "severity": "error 或 warn",
              "why": "不超过 40 字", "suggest": "建议值或做法，不超过 30 字"}}],
  "overall": "pass 或 warn 或 fail"}}"""
    d = chat_json(prompt, system=AUDIT_SYSTEM, scene="audit_record",
                  max_tokens=900, note=record.get("name_zh") or "")
    issues = []
    for it in (d.get("issues") or []):
        if isinstance(it, dict):
            issues.append({
                "field": str(it.get("field") or "")[:24],
                "severity": "error" if str(it.get("severity")).lower() == "error" else "warn",
                "why": str(it.get("why") or "")[:80],
                "suggest": str(it.get("suggest") or "")[:60],
            })
    overall = str(d.get("overall") or ("warn" if issues else "pass")).lower()
    if overall not in ("pass", "warn", "fail"):
        overall = "warn" if issues else "pass"
    return {"issues": issues, "overall": overall}


# ---------------------------------------------------------------- 6 知识库 QA
QA_SYSTEM = (
    "你是知识库编辑。你只为给定条目生成问答对，答案只使用给定信息，"
    "绝不引入外部知识。问题要像真人会问的样子，不要写「请问该国的官方语言是什么」这种考卷腔。"
)


def build_qa(record: dict, n_min: int = 6, n_max: int = 8) -> list[dict]:
    """为单个国家生成检索用的问答对。

    这是「构建知识库」的实体：问答对比整段摘要更适合做检索单元 ——
    用户问一句话，命中一条 QA 就能直接给答案，不必每次都让模型重读全文。

    覆盖四类提问：地理、文化节庆、饮食风物、地标景观，外加一组语言。
    """
    facets = record.get("custom_facets") or {}
    kw = [x.get("v") for x in (facets.get("keywords") or []) if x.get("v")]
    marks = [i.get("caption_zh") or i.get("caption") for i in (record.get("landmark_images") or [])]

    info = {
        "名称": record.get("name_zh"),
        "全称": record.get("name_official"),
        "首都": record.get("capital"),
        "大洲": record.get("continent"),
        "语言": [{"名": l.get("name_zh"), "角色": l.get("role")}
                 for l in (record.get("languages") or [])],
        "简介": (record.get("summary_text") or "")[:600],
        "民俗": (record.get("custom_text") or "")[:500],
        "文化关键词": kw,
        "地标": marks,
    }

    prompt = f"""为「{record.get('name_zh')}」生成 {n_min}~{n_max} 组问答对，用于一个多模态国家文化图谱的检索知识库。

可用信息（这是唯一允许使用的信息源）：
{json.dumps(info, ensure_ascii=False, indent=2)}

要求：
1. 问题像真人会问的，简短口语化。覆盖下列四类，每类至少 1 组：
   - 地理：在哪、周围是什么、面积多大、首都是哪
   - 文化：有什么节日、有什么传统习俗
   - 饮食/风物：吃什么、有什么特产或饮食制度
   - 地标：有什么值得看的建筑或景观
   另外必须有 1 组问及语言（说什么话 / 有哪些方言）。
2. 答案只用上面给的信息，**不编造**。答案 30~80 字，直接给结论，不要复述问题。
3. 每组配 2~4 个检索标签 tags，必须是用户可能打进去的口语词
   （如「长城」「看雪」「节日」「方言」「吃什么」），不要用书面语标签。
4. 若某类信息在给定数据里没有，就不生成那一类，不要硬凑。

只输出 json：{{"qa": [{{"q": "问题", "a": "答案", "tags": ["标签"]}}]}}"""
    d = chat_json(prompt, system=QA_SYSTEM, scene="build_qa",
                  max_tokens=2000, note=record.get("name_zh") or "")

    out = []
    for it in (d.get("qa") or []):
        if not isinstance(it, dict):
            continue
        q = str(it.get("q") or "").strip()
        a = str(it.get("a") or "").strip()
        if not q or not a:
            continue
        tags = [str(t).strip()[:12] for t in (it.get("tags") or []) if str(t).strip()]
        out.append({"q": q[:60], "a": a[:220], "tags": tags[:5]})
    return out[:n_max]


# ---------------------------------------------------------------- 测试夹具

# 说明：结构与真实 Wikidata wbsearchentities + EntityData 返回一致，
# qid 用 DEMO 前缀明确标注这是夹具，不是真实条目号。
CASE_MONT = {
    "target": {"zh": "圣米歇尔山", "en": "Mont Saint-Michel",
               "type": "地标（潮汐岛与本笃会修道院）", "country": "法国"},
    "candidates": [
        {"qid": "DEMO-1", "label": "圣米歇尔山",
         "desc": "法国摩泽尔省的市镇", "country": "法国", "coord": [6.5, 48.9]},
        {"qid": "DEMO-2", "label": "圣米歇尔山",
         "desc": "法国诺曼底大区海岸的潮汐岛，岛上有本笃会修道院，世界遗产",
         "country": "法国", "coord": [-1.51, 48.63]},
        {"qid": "DEMO-3", "label": "圣米歇尔山市",
         "desc": "加拿大魁北克省的一个市镇", "country": "加拿大", "coord": [-73.9, 45.9]},
    ],
    "expect": "DEMO-2",
}

CASE_LOUVRE = {
    "target": {"zh": "卢浮宫玻璃金字塔", "en": "Louvre Pyramid",
               "type": "地标（现代建筑，贝聿铭设计）", "country": "法国"},
    "candidates": [
        {"qid": "DEMO-1", "label": "卢浮宫",
         "desc": "法国巴黎的博物馆，原为王宫", "country": "法国", "coord": [2.337, 48.861]},
        {"qid": "DEMO-2", "label": "卢浮宫金字塔",
         "desc": "卢浮宫拿破仑庭院内的玻璃金字塔，1989 年落成，贝聿铭设计",
         "country": "法国", "coord": [2.336, 48.861]},
    ],
    "expect": "DEMO-2",
}

CASE_CANYON = {
    "target": {"zh": "大峡谷", "en": "Grand Canyon",
               "type": "地标（峡谷地貌，美国亚利桑那州）", "country": "美国"},
    "candidates": [
        {"qid": "DEMO-1", "label": "大峡谷",
         "desc": "美国亚利桑那州由科罗拉多河切割形成的峡谷，国家公园",
         "country": "美国", "coord": [-112.1, 36.1]},
        {"qid": "DEMO-2", "label": "大峡谷村",
         "desc": "美国亚利桑那州可可尼诺县的聚居地", "country": "美国",
         "coord": [-112.15, 36.05]},
        {"qid": "DEMO-3", "label": "大峡谷",
         "desc": "美国宾夕法尼亚州的一条峡谷", "country": "美国", "coord": [-77.5, 41.5]},
    ],
    "expect": "DEMO-1",
}

CASES = [("圣米歇尔山（撞名教堂所在市镇）", CASE_MONT),
         ("卢浮宫玻璃金字塔（与母体建筑区分）", CASE_LOUVRE),
         ("大峡谷（州内同名峡谷）", CASE_CANYON)]


def run_country(iso: str, apply: bool = False, only: str = "all") -> dict:
    """对单个国家跑四类任务。产物先落 data/_llm/ 供人工核对，--apply 才写回正式档案。

    ``only`` 用于单类重跑（如只重抽特征），避免迭代一次就把整轮调用都打一遍。
    """
    rec_path = os.path.join(ROOT, "data", "%s.json" % iso.lower())
    with open(rec_path, encoding="utf-8") as f:
        rec = json.load(f)

    os.makedirs(PREVIEW, exist_ok=True)
    result = {"iso_a2": rec.get("iso_a2"), "name_zh": rec.get("name_zh")}
    want = lambda k: only in ("all", k)  # noqa: E731

    # --- 特征抽取 ---
    if want("facets"):
        print("  [特征抽取] …")
        facets = extract_facets(rec)
        result["facets"] = {k: [x["v"] for x in facets.get(k) or []]
                            for k in ("festivals", "cuisine", "religion",
                                      "architecture", "heritage", "keywords")}
        print("     " + " | ".join("%s %d" % (k[:4], len(result["facets"][k]))
                                   for k in result["facets"]))
        print("     关键词：%s" % "、".join(result["facets"]["keywords"]))
        with open(os.path.join(PREVIEW, "%s.facets.json" % iso.lower()), "w",
                  encoding="utf-8") as f:
            json.dump(facets, f, ensure_ascii=False, indent=2)

    # --- 摘要精炼 ---
    if want("summary"):
        print("  [摘要精炼] …")
        summ = refine_summary(rec)
        result["summary"] = summ
        print("     %d 字 -> %d 字 | 新尾「%s」"
              % (summ["raw_chars"], summ["chars"], summ["new_tail"]))
        with open(os.path.join(PREVIEW, "%s.summary.json" % iso.lower()), "w",
                  encoding="utf-8") as f:
            json.dump(summ, f, ensure_ascii=False, indent=2)

    # --- 民俗成文（用精炼后的摘要 + 已抽特征） ---
    comp = None
    if want("compose"):
        print("  [民俗成文] …")
        comp = compose_history(rec if not want("facets") else dict(rec, custom_facets=facets))
        result["compose"] = comp
        print("     %d 字" % comp["chars"])
        with open(os.path.join(PREVIEW, "%s.compose.json" % iso.lower()), "w",
                  encoding="utf-8") as f:
            json.dump(comp, f, ensure_ascii=False, indent=2)

    # --- 图注翻译（逐张翻译，每张一次调用） ---
    caps = []
    if want("captions"):
        print("  [图注翻译] %d 张 …" % len(rec.get("landmark_images") or []))
        for im in (rec.get("landmark_images") or []):
            # 用 Commons 文件名作英文源：ImageDescription 多半是空的，
            # 而文件名由上传者按主体命名，信息密度更高。
            src = (im.get("title") or "").replace("File:", "").replace("_", " ")
            zh = im.get("caption_zh") or im.get("caption") or ""
            try:
                new = translate_caption(src, zh or rec.get("name_zh") or "")
            except LLMError as e:
                print("     [x] %s：%s" % (src[:30], str(e)[:50]))
                continue
            caps.append({"file": im.get("url"), "landmark_zh": zh, "en": src, "llm_zh": new})
            same = (new.replace(" ", "") == zh.replace(" ", ""))
            print("     %-12s 人工「%s」 / 模型「%s」%s"
                  % (zh[:12], zh, new, "  一致" if same else "  ← 不同"))
        result["captions"] = caps
        with open(os.path.join(PREVIEW, "%s.captions.json" % iso.lower()), "w",
                  encoding="utf-8") as f:
            json.dump(caps, f, ensure_ascii=False, indent=2)

    # --- 知识库问答对 ---
    qa = []
    if want("qa"):
        print("  [知识库 QA] …")
        qa = build_qa(rec)
        result["qa"] = qa
        print("     生成 %d 组" % len(qa))
        for x in qa:
            print("       Q: %-28s tags=%s" % (x["q"][:26], "/".join(x["tags"])))
        with open(os.path.join(PREVIEW, "%s.qa.json" % iso.lower()), "w",
                  encoding="utf-8") as f:
            json.dump(qa, f, ensure_ascii=False, indent=2)

    # --- 数据质检 ---
    if want("audit"):
        print("  [数据质检] …")
        audit = audit_record(rec)
        result["audit"] = audit
        print("     结论 %s，问题 %d 条" % (audit["overall"], len(audit["issues"])))
        for it in audit["issues"]:
            print("       [%s] %s — %s → %s"
                  % (it["severity"], it["field"], it["why"], it["suggest"]))
        with open(os.path.join(PREVIEW, "%s.audit.json" % iso.lower()), "w",
                  encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)

    if apply:
        if "facets" in result:
            rec["custom_facets"] = facets

        # 摘要：原始文本只备份一次，反复 apply 不会把中间产物当原始
        if "summary" in result:
            rec.setdefault("summary_text_raw", rec.get("summary_text"))
            rec["summary_text"] = summ["text"]
            # 保留上一版来源里的 url / title：这是"这段话是从哪来的"的唯一线索，
            # 覆盖掉之后就只剩"llm_refined"，回溯不到条目（实测 2026-10-28 丢过一次）。
            prev_src = rec.get("summary_source") or {}
            rec["summary_source"] = {
                "source": "llm_refined",
                "note": "DeepSeek 基于 Wikipedia 导语 + 人工民俗文本重写；"
                        "口径限定地理与文化，剔除政权更迭与战争史",
                "chars": summ["chars"],
                "derived_from": prev_src.get("source") or None,
                "url": prev_src.get("url") or None,
                "title": prev_src.get("title") or None,
            }
            if summ["chars"] < 300:
                notes = rec.setdefault("review_notes", [])
                if not any("低于 300 字" in n for n in notes):
                    notes.append(
                        "摘要 %d 字，低于 300 字要求：剔除政治史后素材不足。"
                        "补齐办法是采集阶段增取 Wikipedia 的「地理」章节"
                        % summ["chars"])

        # 图注：模型版提升为展示字段，人工版留档可回退、可逐条比对
        if caps:
            for im, c in zip(rec.get("landmark_images") or [], caps):
                if im.get("caption_zh") and not im.get("caption_zh_manual"):
                    im["caption_zh_manual"] = im["caption_zh"]
                im["caption_zh"] = c["llm_zh"]
                im["caption"] = c["llm_zh"]
                im["caption_zh_source"] = "llm_from_commons_filename"

        if comp:
            rec["custom_text"] = comp["text"]
            rec["custom_text_source"] = {
                "source": comp["source"],
                "note": "模型基于维基导语 + 抽取特征成文；只在没有人工稿的国家使用",
                "chars": comp["chars"],
            }

        if qa:
            rec["knowledge_qa"] = qa

        if "audit" in result:
            rec["llm_audit"] = audit
            notes = rec.setdefault("review_notes", [])
            # 上一轮质检留下的记录先清掉，避免同一个问题翻倍堆叠
            notes[:] = [n for n in notes if not n.startswith("LLM 质检[")]
            for it in audit["issues"]:
                notes.append("LLM 质检[%s] %s：%s → %s"
                             % (it["severity"], it["field"], it["why"], it["suggest"]))

        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("  → 已写回 data/%s.json" % iso.lower())

    return result 


def audit_injection_test(iso: str = "cn") -> int:
    """注入已知错误，验证质检不是「一律 pass」。

    一个只会输出 pass 的检查器毫无价值。这里把真数据改成确定错误，
    要求至少检出 3 项 —— 这样「真实数据 pass」才是可信的结论。
    """
    rec_path = os.path.join(ROOT, "data", "%s.json" % iso.lower())
    with open(rec_path, encoding="utf-8") as f:
        rec = json.load(f)

    bad = json.loads(json.dumps(rec))
    bad["capital"] = "上海"
    bad["languages"] = [{"code": "fr", "name_zh": "法语", "role": "official"}]
    bad["landmark_images"] = [{"caption_zh": "自由女神像"}]
    bad["centroid"] = [-33.9, 151.2]

    print("注入 4 个错误：首都=上海 / 语言=法语 / 图注=自由女神像 / 坐标=悉尼")
    a = audit_record(bad)
    print("结论 %s，检出 %d 条：" % (a["overall"], len(a["issues"])))
    for it in a["issues"]:
        print("  [%s] %-16s %s → %s"
              % (it["severity"], it["field"], it["why"], it["suggest"]))

    hit = len(a["issues"])
    ok = hit >= 3 and a["overall"] in ("warn", "fail")
    print("\n%s（要求 ≥3 条且结论非 pass）" % ("[ok] 质检有效" if ok else "[x] 质检过于宽松"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="大模型任务集")
    ap.add_argument("--case", choices=["mont", "louvre", "canyon", "all"], default=None,
                    help="跑实体消歧的测试夹具")
    ap.add_argument("--run", help="对单个 ISO 跑四类任务（CN / FR / US / all）")
    ap.add_argument("--only", default="all",
                    choices=["all", "facets", "summary", "compose", "captions",
                             "audit", "qa"],
                    help="只跑某一类，便于单类迭代")
    ap.add_argument("--apply", action="store_true", help="把结果写回正式档案（默认只预览）")
    ap.add_argument("--audit-injection", metavar="ISO", default=None,
                    help="注入错误验证质检有效性")
    a = ap.parse_args()

    if a.audit_injection:
        return audit_injection_test(a.audit_injection)

    if a.run:
        isos = ["CN", "FR", "US"] if a.run.lower() == "all" else [a.run.upper()]
        allres = []
        for iso in isos:
            print("\n== %s ==" % iso)
            try:
                allres.append(run_country(iso, apply=a.apply, only=a.only))
            except LLMError as e:
                print("  [x] 失败：", e)
                return 1
        print("\n完成 %d 国。预览已写 data/_llm/%s" % (len(allres),
                                                 "（并已写回档案）" if a.apply else ""))
        return 0

    picked = {"mont": [CASES[0]], "louvre": [CASES[1]],
              "canyon": [CASES[2]], "all": CASES}[a.case or "all"]

    ok = 0
    for title, case in picked:
        print("\n== %s ==" % title)
        try:
            r = disambiguate(case["target"], case["candidates"])
        except LLMError as e:
            print("  [x] 调用失败：", e)
            continue
        hit = r["pick"] == case["expect"]
        ok += hit
        print("  选中 : %s（期望 %s）%s" % (r["pick"], case["expect"], "[ok]" if hit else "[x]"))
        print("  置信 : %.2f" % r["confidence"])
        print("  依据 : %s" % r["reason"])
        for x in r["reject"]:
            print("  排除 : %s — %s" % (x["qid"], x["why"]))

    print("\n%d/%d 正确" % (ok, len(picked)))
    return 0 if ok == len(picked) else 1


if __name__ == "__main__":
    sys.exit(main())
