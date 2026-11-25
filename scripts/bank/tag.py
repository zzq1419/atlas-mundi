# -*- coding: utf-8 -*-
"""给真题打标签：主题、难度、以及映射到 83 张知识卡（卡决定解析配图）。

卡片映射走**规则**而不是语义相似度：试过 TF-IDF 最近邻，把"油纸伞推销市场"
判成撒哈拉以南非洲、"巴西大豆"判成亚洲季风区 —— 配错图比不配图更糟。
规则只用两类强证据：
  · 解析/题干里出现该考点的**专有术语**（"消亡边界""副热带高压""背斜"）
  · 出现具体地名（"亚马孙""波斯湾"）
拿不准就不给卡，前端本来就支持没图留空。
"""
import json
import os
import re
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL = os.path.join(ROOT, '_real')

PAPER_FIX = [('新课标iii', '新课标Ⅲ卷'), ('新课标ii', '新课标Ⅱ卷'), ('新课标i', '新课标Ⅰ卷'),
             ('新课标卷', '新课标卷'), ('新课标', '新课标卷'),
             ('全国甲卷', '全国甲卷'), ('全国乙卷', '全国乙卷'), ('高考乙卷', '全国乙卷')]


def norm_paper(p):
    s = (p or '').strip()
    for a, b in PAPER_FIX:
        if s.lower() == a:
            return b
    return s or '高考'


# ---------------------------------------------------------------- 卡片规则
# (卡, 正则, 特异性)  3=具体区域/现象  2=主题级术语  1=泛化兜底
REGION_CARDS = set(['africa-sahel', 'agri-china', 'australia', 'beijing', 'brazil', 'china-climate', 'china-four-regions', 'china-population', 'europe-west', 'flood-drought', 'hk-macao', 'india', 'japan', 'loess-plateau', 'middle-east-oil', 'monsoon-temperate', 'northeast', 'oasis', 'rain-belt', 'region-asia', 'rivers', 'russia', 'sanjiangyuan', 'se-asia', 'taiwan', 'tarim', 'typhoon-coldwave', 'usa', 'yangtze-delta'])

RULES = [
    # —— 具体区域（真题里出现地名就基本能定）
    ('oasis', r'尼罗河|埃及|绿洲农业|阿斯旺', 3),
    ('tarim', r'塔里木|塔克拉玛干|天山.*绿洲', 3),
    ('loess-plateau', r'黄土高原|水土流失|打坝淤地|淤地坝', 3),
    ('sanjiangyuan', r'三江源|中华水塔|澜沧江源', 3),
    ('northeast', r'东北三省|三江平原|松嫩平原|辽河平原|东北平原', 3),
    ('beijing', r'北京市?|京津冀协同', 3),
    ('yangtze-delta', r'长江三角洲|长三角|苏南|浦东', 3),
    ('hk-macao', r'香港|澳门|粤港澳|一国两制', 3),
    ('taiwan', r'台湾岛|台湾省|海峡两岸', 3),
    ('india', r'印度|恒河|德干高原|班加罗尔', 3),
    ('japan', r'日本|东京|本州|北海道渔场', 3),
    ('russia', r'俄罗斯|西伯利亚|莫斯科|贝加尔', 3),
    ('usa', r'美国|密西西比|玉米带|小麦带|五大湖', 3),
    ('brazil', r'巴西|亚马孙|圣保罗', 3),
    ('australia', r'澳大利亚|大自流盆地|墨累|悉尼', 3),
    ('europe-west', r'欧洲西部|西欧|英国|法国|德国|荷兰|意大利|莱茵', 3),
    ('africa-sahel', r'撒哈拉以南|萨赫勒|东非|西非|坦桑尼亚|肯尼亚|尼日利亚', 3),
    ('middle-east-oil', r'中东|波斯湾|霍尔木兹|沙特|阿联酋|石油输出', 3),
    ('se-asia', r'东南亚|马六甲|湄公河|湄南河|橡胶|油棕|印尼|泰国|越南|菲律宾', 3),
    ('region-asia', r'亚洲(?!.*欧洲)|东亚|南亚|中亚', 2),

    # —— 气候类型（气候图上直接对得上）
    ('rainforest', r'热带雨林气候|热带雨林带', 3),
    ('savanna', r'热带草原气候|热带草原带|萨瓦纳', 3),
    ('desert', r'热带沙漠气候|热带荒漠气候', 3),
    ('mediterranean', r'地中海气候', 3),
    ('oceanic', r'温带海洋性气候', 3),
    ('continental', r'温带大陆性气候|亚寒带针叶林气候', 3),
    ('monsoon-temperate', r'温带季风气候', 3),
    ('monsoon-tropical', r'热带季风气候', 3),
    ('polar', r'苔原气候|冰原气候|极地气候', 3),

    # —— 大气
    ('plate', r'板块|消亡边界|生长边界|亚欧板块|太平洋板块|印度洋板块|海沟|俯冲', 2),
    ('fronts', r'冷锋|暖锋|准静止锋|锋面气旋|锋面', 2),
    ('cyclone', r'气旋|反气旋|低压中心|高压中心|副高控制', 2),
    ('pressure-belts', r'气压带|风带|副热带高压|赤道低压|西风带|信风|极地东风', 2),
    ('monsoon', r'季风|夏季风|冬季风|西南季风|东南季风|季风区', 2),
    ('heating', r'大气受热|地面辐射|大气逆辐射|保温作用|削弱作用|太阳辐射', 2),
    ('thermal', r'热力环流|海陆风|山谷风|城市热岛|热岛效应', 2),
    ('china-climate', r'1 月 0℃|一月 0℃|秦岭.{0,3}淮河|我国.{0,6}气温分布|等温线', 2),
    ('rain-belt', r'雨带|梅雨|伏旱|锋面雨带', 2),
    ('typhoon-coldwave', r'台风|寒潮|风暴潮', 3),

    # —— 水文
    ('water-cycle', r'水循环|水汽输送|地表径流|下渗|蒸腾', 3),
    ('current', r'洋流|暖流|寒流|渔场|上升流|厄尔尼诺|拉尼娜', 2),
    ('rivers', r'长江|黄河|地上河|荆江|三门峡|小浪底', 2),

    # —— 地表形态
    ('earthquake', r'地震|震源|震级|烈度|等震线', 2),
    ('landslide-debris', r'滑坡|泥石流|崩塌', 2),
    ('structures', r'背斜|向斜|断层|褶皱|地垒|地堑', 2),
    ('exogenic', r'侵蚀作用|沉积作用|风化作用|搬运作用|流水侵蚀|风力侵蚀|流水沉积|'
                 r'风力沉积|冰川侵蚀|海浪侵蚀', 2),
    ('flood-drought', r'洪涝|旱灾|干旱灾害|防汛|抗旱', 2),
    ('disaster-reduction', r'遥感|GPS|GIS|地理信息系统|全球定位|防灾减灾|监测', 2),

    # —— 人口城市
    ('urbanization', r'城镇化|城市化|城市人口比重|城镇人口', 2),
    ('migration', r'人口迁移|人口流动|迁入|迁出|外出务工|移民', 2),
    ('population', r'人口分布|人口密度|人口增长|人口容量|人口老龄化|出生率|死亡率', 2),
    ('settlement', r'聚落形态|聚落分布|村落形态|聚落区位', 3),
    ('china-population', r'胡焕庸|黑河.{0,4}腾冲|人口地理分界线', 3),
    ('ethnic-language', r'人种|语言|语系|民族分布', 2),

    # —— 文化
    ('religion', r'宗教|佛教|基督教|伊斯兰教|清真寺|教堂', 2),
    ('diffusion', r'文化扩散|文化传播|传入|外传|原产', 2),
    ('service-industry', r'服务业区位|第三产业比重|现代服务业', 3),

    # —— 产业
    ('agri-location', r'农业区位因素|农业地域类型|农业地域|农业生产特点', 3),
    ('industry-location', r'工业区位因素|产业转移|导向型工业|工业地域|工业集聚', 3),
    ('transport', r'交通运输方式|运输方式|交通线布局|交通区位', 3),
    ('land-resource', r'土地资源构成|后备耕地|土地构成|土地利用结构', 3),
    ('agri-china', r'商品粮基地|粮食主产区|南稻北麦|东耕西牧|400 ?毫米', 3),
    ('china-four-regions', r'四大地理区域|北方地区|南方地区|西北地区|青藏地区', 3),
    ('human-land', r'可持续发展|人地关系|人地协调|循环经济|绿色发展', 2),
    ('development', r'发展中国家与发达国家|南北差距|发达国家.{0,4}发展中国家', 3),
    ('china-relief', r'三级阶梯|地势.{0,4}西高东低|青藏高原.{0,6}海拔', 2),
    ('zonality', r'地带性|自然带|垂直带|经度地带|纬度地带|基带', 2),
    ('soil', r'土壤剖面|土壤有机质|腐殖质|黑土|红壤|盐碱化|土壤形成', 3),
]


def topic_of(it):
    """在题干+选项里找证据，返回 (卡, 分数)。

    只在**题干和选项**里找，不碰材料 —— 这一条是这轮踩出来的：
      · “巴西大豆产量比美国强” 材料里美国出现三次，配美国地图是错的；
      · “四城市人口变化” 材料里列了北京，配北京地图也是错的；
      · “花基菜基鱼塘” 材料提了两次土壤，配土壤剖面更离谱。
    材料是背景，题干问的才是考点。宁可少配，不可配错。
    """
    qtext = it['q'] + ' ' + ' '.join(it['opts'])
    hits = []
    for card, pat, lv in RULES:
        if re.search(pat, qtext):
            hits.append((3.0 * lv, card))
    if not hits:
        return '', 0
    hits.sort(reverse=True)
    if len(hits) > 1 and hits[0][0] == hits[1][0]:
        return '', 0                  # 打平 → 拿不准
    # 并列出现两个区域卡（“巴西比美国强”），说明题目是跨国比较，配哪国图都是误导
    top = hits[0][0]
    if sum(1 for sc, c in hits if sc == top) > 1:
        return '', 0
    return hits[0][1], hits[0][0]


THEME_KW = [
    ('地球运动', r'地方时|区时|时区|日界线|太阳高度|昼夜|日出|日落|公转|自转|黄赤交角|晨昏线'),
    ('地球与地图', r'等高线|比例尺|图例|经纬网|方位|地形图'),
    ('大气与天气', r'气候|气温|气压|锋面|气旋|反气旋|季风|干旱|寒潮|台风|天气|降水'),
    ('水与海洋', r'洋流|渔场|水循环|径流|蒸发|河流|湖泊|地下水|海冰|咸潮|流域'),
    ('自然带与生态', r'自然带|植被|土壤|地带性|生物多样性|生态|森林|草原|荒漠化'),
    ('地表形态', r'地貌|侵蚀|沉积|断层|褶皱|滑坡|泥石流|板块|火山|地震|三角洲|冲积'),
    ('人口与城市', r'人口|城市|城镇化|聚落|迁移|老龄化|住宅|通勤'),
    ('文化', r'文化|宗教|语言|民族|旅游|饮食|服饰|节日'),
    ('产业与区域', r'农业|工业|产业|区位|交通|铁路|港口|市场|出口|区域|发展'),
]


def guess_theme(text):
    for name, pat in THEME_KW:
        if re.search(pat, text):
            return name
    return '产业与区域'


# ---------------------------------------------------------------- 难度
HARD = re.compile(r'计算|地方时|时区|区时|正午太阳高度|太阳高度|日出日落|昼夜长短|比例尺|等高距|'
                  r'等压线|等温线|等降水量|气压梯度|相对高度')
ASK = re.compile(r'主要目的|主要原因是|是因为|原因是|影响是|反映了|表明|说明|推测|判断|'
                 r'可以得出|有利于|不利于|主导因素|首要|根本')


def difficulty(it):
    s = 5.2
    L = len(it['material']) + len(it['q'])
    if L > 300:
        s += 0.9
    elif L > 170:
        s += 0.4
    txt = it['material'] + it['q'] + ''.join(it['opts'])
    if HARD.search(txt):
        s += 1.1
    if ASK.search(it['q']):
        s += 0.4
    if len(re.findall(r'[①②③④]', txt)) >= 4:
        s += 0.5                      # 组合选项要逐个判断，实际更难
    if it['year'] >= '2021':
        s += 0.2                      # 新高考整体偏难
    if it['year'] <= '2013':
        s -= 0.3
    return round(min(9.5, max(2.8, s)), 1)


# 自动规则会误伤：'冬季风' 匹配到'冬季风力'、'水土流失' 崩到长白山林线题、
# 选项里出现'防地震'就把地下工厂题配成地震图。逐条复核后把这些清掉。
# 键是题干前 12 字，值固定为 ''（不给图）。留空比配错好。
DROP = {
    '该公司在中国建零部件生产厂': '考点是产业转移，配日本地图无帮助',
    '长白山西北坡比其他坡向冻害高发': '“冬季风”误匹配“冬季风力”',
    '气候变暖但冻害加剧的原因可能': '冻害题，水循环图不及物',
    '兰斯塔德空间规划的实施，可以': '城市规划题，人口分布图无帮助',
    '与岐阜相比，大连地下工厂的': '选项“防地震”误命中，考点是工业区位',
    '该公路山区段定期封路禁行主要': '选项“泥石流”误命中，实际考积雪封路',
    '在气候变暖背景下，长白山北坡': '选项“水土流失”误命中',
    '1870年后，美国用水来源结构': '用水结构题，农业带图无帮助',
}


def main():
    bank = json.load(open(os.path.join(ROOT, 'assets/bank/geo.json'), encoding='utf-8'))
    meta = {}
    for x in bank['items']:
        c = x.get('card')
        if c and c not in meta:
            meta[c] = (x.get('theme'), x.get('cardName'))

    real = json.load(open(os.path.join(REAL, 'parsed.json'), encoding='utf-8'))
    out, hit = [], collections.Counter()
    for it in real:
        card, sc = topic_of(it)
        if card not in meta:          # 规则写错卡名时兜底
            card = ''
        # 主题独立判定，不跟卡走：区域卡（usa/japan…）的 theme 统一是"产业与区域"，
        # 若继承过来，一道"美国气候"的题会被归进产业，筛选时找不到。
        theme = guess_theme(it['material'] + it['q'] + ' '.join(it['opts']) + (it.get('exp') or ''))
        if card:
            hit[card] += 1
        out.append({
            'id': 'gk-%s-%s-%s' % (it['year'], re.sub(r'\W+', '', it['paper']) or 'x', it['no']),
            'type': 'choice',
            'grade': '高中',
            'theme': theme,
            'card': card,
            'cardName': meta[card][1] if card else '',
            'diff': difficulty(it),
            'score': it.get('score') or 4,
            'material': it['material'],
            'q': it['q'],
            'opts': it['opts'],
            'ans': it['ans'],
            'exp': it['exp'] or '本题源数据未收录解析，答案见上方标注。',
            'year': it['year'],
            'paper': norm_paper(it['paper']),
            'no': it['no'],
            'src': '%s 年%s · 第 %s 题' % (it['year'], norm_paper(it['paper']), it['no']),
            'level': sc,
        })

    for r in out:
        for k in DROP:
            if r['q'].startswith(k):
                r['card'], r['cardName'] = '', ''
                break

    json.dump(out, open(os.path.join(REAL, 'tagged.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('题数', len(out))
    print('有卡', sum(1 for r in out if r['card']), '/', len(out))
    print('主题', collections.Counter(r['theme'] for r in out).most_common())
    print('卡片', hit.most_common(20))


if __name__ == '__main__':
    main()
