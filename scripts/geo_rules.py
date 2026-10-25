#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""绘制规则（采集与重绘共用，单一事实来源）

为什么单独一个文件：
    「哪些要素要并入中国版图」这条规则同时被 collect.py（采集时提取边界）
    和 build_geo.py（重新生成 geo/*.geojson）使用。写两处必然会漂移，
    漏一处就会出现「中国地图没有台湾」这种问题。
"""

# 主权归属合并表。
# Natural Earth 把中国台湾、中国香港、中国澳门画成独立要素（各有自己的 ISO 码），
# 但在中国版图上它们必须绘制为中国的一部分 —— 缺失即属错绘。
# 命名一律用「中国台湾」「中国香港」「中国澳门」，
# 且不得进入「国家」列表参与排序（交接文档第 6 节第 6 条）。
MERGE_INTO = {
    "CN": ["TW", "HK", "MO"],
}

# 永远不单独作为「国家」出现的 ISO 码（它们已被并入父级版图）
NEVER_AS_COUNTRY = {code for codes in MERGE_INTO.values() for code in codes}

# 展示用中文名（避免直接用 Natural Earth 的 NAME_ZH）
DISPLAY_NAME = {
    "CN": "中国",
}

# 说明：本项目的国界来自 Natural Earth 50m 的行政边界，是中国版图轮廓的**简化示意**，
# 不等同于标准地图。正式对外发布的地图产品须使用自然资源部标准地图服务
# （bzdt.ch.mnr.gov.cn）的底图或经审核的地图数据。
COMPLIANCE_NOTE = (
    "国界取自 Natural Earth 50m 简化轮廓，已按中国版图将中国台湾、中国香港、"
    "中国澳门并入绘制；本图为教学用途的示意轮廓，非标准地图。"
)
