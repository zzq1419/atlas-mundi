# -*- coding: utf-8 -*-
"""离线集成测试：用夹具驱动 collect.py 的网络层，验证解析链路。"""
import json
import importlib.util
import os

# 路径一律用 os.path 拼，不要写死反斜杠 —— CI 跑在 Linux 上，
# "scripts\collect.py" 在那里会被当成一个含反斜杠的文件名，直接找不到。
HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


spec = importlib.util.spec_from_file_location(
    "c", os.path.join(HERE, "collect.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def snak(v):
    return [{"mainsnak": {"snaktype": "value", "datavalue": {"value": v}}}]


ENTITY = {"entities": {"Q148": {
    "labels": {"zh": {"value": "中华人民共和国"}, "en": {"value": "People's Republic of China"}},
    "claims": {
        "P297": snak("CN"),
        "P298": snak("CHN"),
        "P625": snak({"latitude": 35.0, "longitude": 103.0}),
        "P36": snak({"id": "Q956"}),
        "P30": snak({"id": "Q48"}),
        "P37": (snak({"id": "Q727694"}) + snak({"id": "Q7850"})
                + snak({"id": "Q835866"}) + snak({"id": "Q24841726"})
                + snak({"id": "Q9186"})),
        "P18": snak("The_Great_Wall_of_China_at_Jinshanling-edit.jpg"),
        "P443": [{"mainsnak": {"snaktype": "somevalue"}}],
    },
    "sitelinks": {"zhwiki": {"title": "中国"}},
}}}

LABELS = {"entities": {
    "Q956": {"labels": {"zh": {"value": "北京"}}},
    "Q48": {"labels": {"zh": {"value": "亚洲"}}},
    "Q7850": {"labels": {"zh": {"value": "汉语"}}},
    "Q9186": {"labels": {"zh": {"value": "粤语"}}},
    "Q727694": {"labels": {"zh": {"value": "现代标准汉语"}}},
    "Q835866": {"labels": {"zh": {"value": "中国语言"}}},
    "Q24841726": {"labels": {"zh": {"value": "普通话"}}},
}}

EXTRACT = ("中华人民共和国是位于亚洲东部、太平洋西岸的国家，陆地面积约960万平方公里。"
           "地势西高东低，呈三级阶梯分布，西南为青藏高原，中部为高原与盆地，东部为平原与丘陵。"
           "长江与黄河自西向东注入东海与渤海。全国划分为34个省级行政区，首都为北京。"
           "汉语普通话为国家通用语言，粤语、吴语、闽南语等方言在各自区域广泛使用。"
           "中国是世界文明古国之一，有文字可考的历史近三千年。长城、故宫、秦始皇陵及兵马俑坑、"
           "莫高窟、布达拉宫等已被列入世界文化遗产名录。") * 2

IMAGEINFO = {"query": {"pages": {"1": {
    "title": "File:The Great Wall of China at Jinshanling-edit.jpg",
    "imageinfo": [{
        "url": "https://upload.wikimedia.org/x.jpg",
        "thumburl": "https://upload.wikimedia.org/x_900.jpg",
        "extmetadata": {
            "LicenseShortName": {"value": "CC BY-SA 4.0"},
            "Artist": {"value": "<a href='#'>Severin.stalder</a>"},
        },
    }],
}}}}


def fake_get(url, timeout=45, retries=3, accept=None):
    if "Special:EntityData" in url:
        return json.dumps(ENTITY).encode()
    if "wbgetentities" in url:
        return json.dumps(LABELS).encode()
    if "prop=extracts" in url:
        return json.dumps({"query": {"pages": [{"title": "中国", "extract": EXTRACT}]}}).encode()
    if "prop=images" in url:
        return json.dumps({"query": {"pages": [{"images": [
            {"title": "File:China_Flag_icon.png"},
            {"title": "File:Forbidden_City_Beijing.jpg"},
            {"title": "File:Great_Wall.jpg"},
        ]}]}}).encode()
    if "imageinfo" in url:
        return json.dumps(IMAGEINFO).encode()
    raise AssertionError("未预期请求: " + url[:90])


c.http_get = fake_get
results = []


def chk(name, got, want):
    ok = got == want
    results.append(ok)
    print(("  ok    " if ok else "  FAIL  ") + name + "  got=" + repr(got))


notes = []
wd = c.fetch_wikidata("CN", None, notes)
chk("qid", wd.get("qid"), "Q148")
chk("iso_a2", wd.get("iso_a2"), "CN")
chk("iso_a3", wd.get("iso_a3"), "CHN")
chk("首都（标签解析）", wd.get("capital"), "北京")
chk("大洲（标签解析）", wd.get("continent"), "亚洲")
chk("坐标", wd.get("centroid"), [103.0, 35.0])
chk("语言去重后数量", len(wd.get("languages") or []), 2)
chk("语言去重保留项", [l["name_zh"] for l in wd.get("languages") or []],
    ["现代标准汉语", "粤语"])
chk("短名优先", wd.get("name_zh"), "中国")
chk("全称另存", wd.get("name_official"), "中华人民共和国")
chk("P443 somevalue 跳过", wd.get("_audio_files"), [])
chk("卢森堡语发音被拒", c.is_zh_audio("Lb-China.ogg"), False)
chk("中文发音被采纳", c.is_zh_audio("Zh-中国.ogg"), True)
chk("英文发音被拒", c.is_zh_audio("En-us-China.ogg"), False)
chk("维基标题", wd.get("_wiki_title"), "中国")

s = c.fetch_summary("中国", notes)
chk("摘要在 300~500", 300 <= len(s["text"]) <= 500, True)
chk("摘要句末截断", s["text"].rstrip().endswith("。"), True)

chk("正文配图过滤 icon", c.article_images("中国"),
    ["Forbidden_City_Beijing.jpg", "Great_Wall.jpg"])

meta = c.lookup_meta(c.commons_imageinfo(["The_Great_Wall_of_China_at_Jinshanling-edit.jpg"]),
                     "The_Great_Wall_of_China_at_Jinshanling-edit.jpg")
chk("下划线/空格归一命中", meta is not None, True)
chk("授权解析", (meta or {}).get("license"), "CC BY-SA 4.0")
chk("作者去 HTML", (meta or {}).get("artist"), "Severin.stalder")

# 图片过滤：踩过两次（Locator map / Location Map svg），必须回归保护
BAD_CASES = [
    ("United States - Location Map (2013) - USA - UNOCHA.svg", True),
    ("Locator map of United States.png", True),
    ("Flag of the United States.svg", True),
    ("Flag_of_France.svg", True),
    ("Great Seal of the United States (obverse).svg", True),
    ("National emblem of France.svg", True),
    ("Coat of arms of France.svg", True),
    ("Map of USA states.png", True),
    ("The Great Wall of China at Jinshanling-edit.jpg", False),
    ("Paris from the Arc de Triomphe, 25 April 2014.jpg", False),
    ("Grand Canyon Hopi Point.jpg", False),
    ("US Capitol west side.JPG", False),
    ("Statue of Liberty 7.jpg", False),
]
for name, want in BAD_CASES:
    chk(("拦截 " if want else "放行 ") + name[:34], c.is_bad_image(name), want)

# 地标选图打分：踩过两次（主体不在画面 / 5:1 全景长条 / 分辨率过低），必须回归保护
F = _load("atlas_fill", "fill_images.py")

SCORE_CASES = [
    ("Tour Eiffel from Champ de Mars.jpg",
     {"width": 1600, "height": 1067, "aspect": 1.5}, "eiffel", True),
    ("Aerial view of Champ de Mars, Paris.jpg",
     {"width": 1600, "height": 1067, "aspect": 1.5}, "eiffel", False),
    ("Forbidden City Beijing panorama.jpg",
     {"width": 6000, "height": 1200, "aspect": 5.0}, "supreme harmony", False),
    ("Hall of Supreme Harmony, Forbidden City.jpg",
     {"width": 1800, "height": 1200, "aspect": 1.5}, "supreme harmony", True),
    ("Potala Palace, Lhasa.jpg",
     {"width": 442, "height": 643, "aspect": 0.688}, "potala", False),
    ("Potala Palace Lhasa Tibet.jpg",
     {"width": 2048, "height": 1365, "aspect": 1.5}, "potala", True),
    ("Statue of Liberty front.jpg",
     {"width": 1200, "height": 1600, "aspect": 0.75}, "statue of liberty", True),
]
for _name, _meta, _must, _want in SCORE_CASES:
    chk(("收 " if _want else "拒 ") + _name[:32], F.score(_name, _meta, _must)[0] is not None, _want)

print("\n%d / %d 通过" % (sum(results), len(results)))
if notes:
    print("notes:")
    for n in notes:
        print("  -", n)
