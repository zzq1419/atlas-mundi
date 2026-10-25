# 寰宇图志 · Atlas Mundi

> **《寰宇图志：3D 地球上的多模态国家文化图谱》**
> 数据采集与融合技术 · 课程实践项目

---

## 项目一句话

一个 3D 地球交互网站：点击地球上的国家/地区，弹出该地的**地标影像、语言方言、地理位置、历史民俗文字**四类内容。

核心价值不在 3D 视觉效果，而在于**多模态 + 多源异构数据的采集与融合**。

## 技术栈（明确不做的事）

| 选型 | 结论 |
| --- | --- |
| 前端 | 纯 HTML + 原生 JS + three.js / globe.gl（CDN 引入） |
| 构建工具 | **不使用**，无 React / Vue / Vite / TypeScript |
| 后端 | **不做**，纯静态 |
| 数据库 | **不做**，数据只读，前端直接 fetch JSON |
| 托管 | GitHub Pages |
| TTS | 构建期离线生成 mp3，**不在运行时调用** |

## 目录

```
atlas-mundi/
├── index.html      # 单文件前端（阶段 A+B：托管与跨域验证）
└── README.md
```

后续阶段新增：

```
├── data/           # 各国 JSON（iso_a2.json）
├── assets/         # 图片、音频（初期随仓库，后期迁对象存储）
├── scripts/        # 采集脚本
└── geo/            # Natural Earth 50m 国界 GeoJSON
```

## 实施阶段

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| A | 静态托管跑通，公网可访问 | ✅ |
| B | 跨域图片 / 音频取用验证 | 🔄 |
| C | 中国 / 法国 / 美国 三国数据 + 卡片页 | ⬜ |
| D | 3D 地球 + 搜索框 + 侧边列表 | ⬜ |
| E | 扩至 100+ 国家/地区 | ⬜ |

## 数据源

| 源 | 提供 |
| --- | --- |
| Wikidata（SPARQL） | ISO 码、坐标、语言、首都、大洲 |
| Wikipedia REST | 多语言摘要、缩略图 |
| Wikimedia Commons | 图片、语言发音（须取授权字段） |
| Natural Earth 50m | 国界多边形 |
| TTS（华为云 / Edge-TTS） | 兜底发音 |

主键：对外 `iso_a2`，内部 `QID`。字段映射与实体对齐规则见交接文档第 5、6 节。

## 数据契约（每国一条 `/data/{iso}.json`）

对外主键 `iso_a2`；`/data/index.json` 只放渲染入口卡需要的字段，详情按主键再拉一次。

| 字段 | 状态 | 说明 |
| --- | --- | --- |
| `iso_a2` / `iso_a3` / `qid` | ✅ | 主键与回溯标识 |
| `name_zh` / `name_en` / `name_local` | ✅ | 三语并列 |
| `capital` / `continent` | ✅ | 面板副标题与分组 |
| `centroid` | ⚠️ 人工估算 | 待换 Wikidata P625 |
| `languages[]` | ✅ | 含 `role` 与各自 `audio_status` |
| `landmark_images[]` | ✅ | 含 `caption` / `license` / `load_verified` |
| `image_license` | ❌ 未取到 | 必须从 Commons `extmetadata` 读，取不到即丢弃该图 |
| `summary_text` | ✅ 人工撰写 | 待换 Wikipedia REST + LLM 改写 |
| `custom_text` | ✅ 人工撰写 | 历史民俗摘编 |
| `audio_url` | ❌ 待 TTS | 构建期生成 mp3 后回填，`audio_source` 改 `tts` |
| `geometry` | ❌ 待采集 | 阶段 D 从 Natural Earth 50m 取 MultiPolygon |
| `sources[]` / `review_notes[]` | ✅ | 过程留痕，供报告"情感态度"与"建模算法调研"引用 |

`review_notes` 里逐条列出未达标项，**不隐藏缺口**：缺授权字段的图不进正式数据集，缺音频的走 TTS 兜底，缺边界的微国家用 `centroid` 渲染圆点。

## 本地预览

直接双击 `index.html` 即可，但 `file://` 协议下浏览器禁止 `fetch`，数据区会提示失败 —— 这是浏览器安全策略，属正常。
要看完整效果请用公网地址，或在本目录起一个本地服务器：

```bash
python -m http.server 8000
# 然后访问 http://localhost:8000/
```

