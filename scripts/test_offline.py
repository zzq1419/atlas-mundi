# -*- coding: utf-8 -*-
"""离线集成测试：用夹具驱动 collect.py 的网络层，验证解析链路。"""
import json
import importlib.util

spec = importlib.util.spec_from_file_location("c", r"scripts\collect.py")
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

print("\n%d / %d 通过" % (sum(results), len(results)))
if notes:
    print("notes:")
    for n in notes:
        print("  -", n)
