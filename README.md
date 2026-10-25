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

## 采集（构建期，跑在本机）

```bash
python scripts/collect.py CN          # 采集一国
python scripts/collect.py CN --geo    # 额外抓 Natural Earth 50m 边界（首次约 24MB）
```

Windows 上直接双击启动器即可，脚本只用标准库，不需要 pip 装任何东西：

| 启动器 | 作用 |
| --- | --- |
| `采集中国.bat` | 采 CN |
| `采集法国美国.bat` | 采 FR + US，一国失败不影响另一国 |
| `重新采集.bat` | 输入任意 ISO 码重采单国（P18 挂地图/国旗时用） |
| `补齐地标图.bat` | 按 `data/landmarks.json` 的人工清单补齐各国地标图（中文图注） |

换其他国家：改启动器里的 ISO 码，或命令行 `python scripts/collect.py DE`。

**必须在开代理的情况下跑** —— Wikimedia 系（`commons` / `upload` / `query.wikidata` / `zh.wikipedia`）在国内直连与代理两种模式下都不通。

采集流程与字段归属：

| 步骤 | 接口 | 产出 |
| --- | --- | --- |
| 1 | Wikidata SPARQL（P297/P298/P625/P36/P30/P37/P18/P443） | ISO 码、坐标、首都、大洲、官方语言、代表图、发音文件 |
| 2 | Wikipedia REST | 中文摘要，自动压到 300~500 字 |
| 3 | Commons `imageinfo` + `extmetadata` | 图片直链 + **真实授权**，素材下载进 `assets/{iso}/` |
| 4 | Natural Earth 50m（`--geo`） | 国界 MultiPolygon，提取后存 `geo/{iso}.geojson`（中国 2662 顶点 / 67KB） |

授权三级策略（不因缺授权就一张图都没有）：

| 级 | 情况 | 处理 |
| --- | --- | --- |
| A | `extmetadata` 有授权 | 写入 `license`，`license_status=ok`，页面显示「CC BY-SA 4.0 · 作者」 |
| B | 无授权但有文件直链 | **保留图片**，`license_status=unknown`，页面标「授权待确认」并保留来源文件名 |
| C | 连文件直链都拿不到 | 丢弃，记入 `review_notes` |

B 级存在的理由：Wikimedia 上绝大多数文件都有授权，取不到通常是 `extmetadata` 解析异常而非真的无授权。为此让一个国家一张图都没有，代价远大于「标注来源 + 授权待确认」。**来源必须留痕**，这是学术诚实的最低线。

另外两条不变量：

2. **素材落本地**，JSON 里存相对路径 —— 断网、无代理也能演示
3. **失败不中断**，缺口逐条写入 `review_notes`，同步更新 `data/index.json` 的模态就绪位

连通性体检：`python scripts/collect.py CN --check`。四个域名（Wikidata / 中文维基 / Commons / upload 图床）逐个探测；**全部不通时脚本直接中止，不会覆盖已有 JSON**。

构建期 TTS：`python scripts/tts.py CN`

两种引擎，一条命令搞定：

| 引擎 | 说明 |
| --- | --- |
| `edge`（默认） | 微软 Edge 朗读接口，免费无 key，支持粤语 `zh-HK-HiuMaanNeural`、法语、英语等，输出 24kHz MP3（约 30~40KB / 句） |
| `sapi` | Windows 本地 SAPI，完全离线，但本机只有普通话音色（Huihui），输出 22.05kHz WAV |

`--engine auto` 会先试 edge，失败自动回落 sapi。

为什么不用 Wikidata 的 P443：**P443 只保证「有发音文件」，不保证语种**。中国 Q148 的首个发音是
`Lb-China.ogg` —— 卢森堡语读的 China。所以采集只采信文件名带 `zh-` / `chinese` / `中文` 的发音，
区域语言（粤语）一律走 TTS。

语音内容约定：**每个语言一条 5~6 秒的句子，不是干念国名**。念两三个字播放条一闪就没，演示时看不出
「这是语音模态」，等于白做一条模态。文案优先取 `languages[].tts_text`，其次取 `scripts/tts.py` 里的
`PHRASES` 句库，最后才用模板拼装 —— 手写句子比模板自然，也方便改。

没有对应音色的语种（如布列塔尼语 `br`）**明确跳过并写入 `review_notes`**，不用邻近语种硬读冒充。

图片：原图下载后统一转 WebP 双尺寸（详情 760px q72 / 缩略 400px q74），960×615 的 272KB JPEG →
108KB + 27KB，减半。原图不入库，`remote_url` 保留可回溯。

离线测试：`python scripts/test_offline.py` —— 用夹具驱动解析链路，不联网，覆盖标签解析、坐标解包、摘要截断、配图过滤、标题归一与授权解析。

## 地标图为什么不再靠自动挑选

Wikidata 的 P18 每国只给 **1 张**「代表图」，而且不保证是地标 —— 美国 Q30 给的是
`United States - Location Map (2013) - USA - UNOCHA.svg`（定位地图）。自动挑选也无法保证
挑中「最著名的那一张」，更给不出中文图注。

所以地标改成**人工指定清单**：`data/landmarks.json` 里每个国家列 4 条
`{zh: 中文图注, kw: Commons 检索关键词}`，`fill_images.py` 按关键词去 Commons 搜图，
过滤掉地图/旗帜/徽章、要求有授权且宽度 ≥ 800px，取回后把 `caption_zh` 写死。

顺序即展示顺序，**第一张是封面**。想换图只改这个 JSON，不用动代码。

## 采集之后的三个收尾步骤

采完还要压图、配语音、重算索引，三条命令：

```bash
python scripts/optimize_images.py --all   # 大图转 WebP 双尺寸，改写 JSON 路径
python scripts/tts.py CN                  # 逐国生成语音（有音色的语种才生成）
python scripts/sync_index.py              # 由 data/*.json 反推 index.json 的模态位与状态
```

`sync_index.py` 是必需的：`collect.py` 只按采集当时的字段写一次 `index.json`，
之后补的边界、补的语音它并不知道。让 `index.json` 永远由档案反推，避免手工对不上。

## 本地预览

直接双击 `index.html` 即可，但 `file://` 协议下浏览器禁止 `fetch`，数据区会提示失败 —— 这是浏览器安全策略，属正常。
要看完整效果请用公网地址，或在本目录起一个本地服务器：

```bash
python -m http.server 8000
# 然后访问 http://localhost:8000/
```

