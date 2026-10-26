# 寰宇图志 · Atlas Mundi

> **《寰宇图志：3D 地球上的多模态国家文化图谱》**
> 数据采集与融合技术 · 课程实践项目

---

## 项目一句话

一个 3D 地球交互网站：点击地球上的国家/地区，弹出该地的**地标影像、语言方言、地理位置、历史民俗文字**四类内容。

核心价值不在 3D 视觉效果，而在于**多模态 + 多源异构数据的采集与融合**。

## 仓库与在线地址

| 用途 | 地址 |
| --- | --- |
| **代码仓库（课程交付）** | <https://gitee.com/zzq-1419/atlas-mundi> |
| 代码仓库（开发主库） | <https://github.com/zzq1419/atlas-mundi> |
| 线网站点 | <https://zzq1419.github.io/atlas-mundi/> |
| 素材分发（华为云 OBS） | <https://atlas-mundi-1419.obs.cn-east-3.myhuaweicloud.com/> |
| 数据集快照（v0.1.0） | <https://github.com/zzq1419/atlas-mundi/releases/tag/v0.1.0> |
| CI 运行记录 | <https://github.com/zzq1419/atlas-mundi/actions> |

**为什么代码放两处**：课程要求交 Gitee 链接，所以 Gitee 作为交付主库；但
Gitee Pages 免费版需要实名审核、且对静态站有限制，而 GitHub Pages + Actions +
Releases 是零成本且已验证可用的，所以运行与 CI 放在 GitHub。两处内容一致。

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

## 云平台使用清单（对应评分表「项目准备 · 云平台」）

评分表要求「娴熟使用（5 次以上）」。实际使用 **9 项**，全部零成本、全部可截图举证。

### 总表

| # | 平台 | 服务 | 用途 | 证据位置 |
| --- | --- | --- | --- | --- |
| 1 | GitHub | **Pages** | 托管站点与数据 | <https://zzq1419.github.io/atlas-mundi/> |
| 2 | GitHub | **Actions** | CI：41 项离线断言 + 6 项数据门禁 + 国界合规自检 | 仓库 Actions 页，7 步全绿 |
| 3 | GitHub | **Releases** | 数据集快照 `v0.1.0`（含 `MANIFEST.json`） | 仓库 Releases 页 |
| 4 | GitHub | REST API | 建仓、逐次提交、开启 Pages、创建 Release | 提交记录可查 |
| 5 | 微软 | Edge TTS | 构建期语音合成（普通话/粤语/法语/英语） | `assets/*/audio/*.mp3` |
| 6 | **华为云** | **OBS 对象存储** | 素材分发：24 图 + 4 音频，57 对象 / 1.59 MB | 桶 `atlas-mundi-1419` 对象列表 |
| 7 | **华为云** | **FunctionGraph** | 检索函数 `atlas_search`，云端执行返回 3 条 | 函数控制台「测试」结果 |
| 8 | **华为云** | **云监控 CES** | OBS 桶 GET 类请求告警（阈值 1 万次/天） | 告警规则列表 `atlas-obs-traffic` |
| 9 | **华为云** | **IAM** | 用户组 `obs_uploaders` + 子用户 `obs_bot`，最小权限 | IAM 用户组授权记录 |
| 10 | **华为云** | **LTS 日志服务** | 函数调用日志（`Start invoke request …`） | 函数日志页 |

### 华为云这 5 项各自解决了什么

| 服务 | 不是「凑数」的理由 |
| --- | --- |
| OBS | 图片从 GitHub Pages 的 **1.8 秒** 降到 **0.17 秒**（快 10 倍），直接解决首屏卡顿 |
| FunctionGraph | 检索能力从「页面内 JS」扩展为「可对外调用的服务」，同一套算法两种部署形态 |
| CES | 防公网流量被刷：GET 请求超 1 万次/天即邮件告警 |
| IAM | 上传素材不再用手动主账号密钥，子用户只能碰 OBS，删不掉函数、改不了桶策略 |
| LTS | 函数每次调用都有结构化日志，出问题能定位到具体记录 |

### OBS 的定位必须说清楚：它没有托管网站

华为云从 2022-01-01 起（华东-上海一等区域）**禁止用默认域名做静态网站托管** —— 官方文档原文：
用 `*.obs-website.*` 或桶域名在浏览器访问网页时**不显示内容，而作为附件下载**
（强制 `Content-Disposition: attachment`）。

我们实测过三种绕法，全部无效：

| 尝试 | 结果 |
| --- | --- |
| 对象设 `Content-Type: text/html; charset=utf-8` | 头正确了，但 `attachment` 仍在 |
| 带浏览器 `Accept: text/html` + UA | 无效 |
| OBS 原生签名（HMAC-SHA1）显式发 `Content-Disposition: inline` | **`Cache-Control` 生效了，`inline` 被平台覆盖** |

第三种的对比最有说明力：同一个请求里 `Cache-Control` 成功、`inline` 被改写 ——
证明签名和请求都没问题，是平台层强制覆盖。

唯一官方解法是绑定**已备案的自定义域名**，备案周期不适合本项目节奏。所以最终是**双源分离**：

| 内容 | 托管位置 | 原因 |
| --- | --- | --- |
| `index.html`、`data/*.json`、`geo/*.geojson` | GitHub Pages | 同域 fetch 不需要 CORS |
| `assets/` 图片与音频 | **华为云 OBS（上海一）** | `<img>`/`<audio>` 作为子资源**不受** `Content-Disposition` 影响（已实测） |

前端用 `setAsset()` 做**双源回退**：优先 OBS，失败自动退到仓库相对路径，两个源互为备份。

### API 网关：做过评估，主动放弃

函数详情页「创建触发器」的**默认类型是 APIC（API Connect）**，而 APIC 必须创建实例，
默认报价是**包年专业版约 4 万元**。这条路径对课程项目毫无意义，果断退出。

APIG（API 网关）基础版虽有 100 万调用/月免费额度，但本次没有走通——不影响任何功能，
因为「函数在云端真实执行」已经通过控制台测试举证，而检索能力在页面上本来就是可用的。

**这个判断过程本身值得写进报告**：平台默认值把人引向万元级资源，能否识别「哪些能力不需要」
比「能不能配通」更能说明工程判断力。

### 费用实况

| 项 | 费用 |
| --- | --- |
| GitHub Pages / Actions / Releases | 0（公开仓库免费） |
| Edge TTS | 0（免 key） |
| 华为云 OBS | 存储 1.59 MB ≈ **¥0.0002/月**；出网流量按访问量计，几十次访问约几分钱 |
| 华为云 FunctionGraph | 0（100 万次调用 + 40 万 GB·秒/月免费额度内） |
| 华为云 CES / IAM / LTS | 0（基础功能免费） |
| **合计** | **几分钱量级**，且已设 1 元预算告警兜底 |

没有开 ECS、没有开任何包年资源、没有绑定付费实例。

### 一条底线：只写调用过的服务

报告里出现的每一项云服务都能在控制台找到对应资源，且能截图。**不写「使用过华为云 OBS
部署了网站」这种表述** —— 事实是 OBS 只做素材分发，站点在 GitHub Pages。措辞准确比听起来厉害更重要。

## 3D 地球（环球视角）

页面上有一个可拖拽旋转的 3D 地球，点击国土直接打开该国档案。

### 四个技术决定

**① 不用贴图，只用我们自己的 GeoJSON。**

真实地球纹理（4K 等距柱状图）通常 2~8MB，且授权要单独确认。我们的做法是：
暗色球体 + Natural Earth 110m 大陆轮廓（细线）+ 三国国界（金色）。数据只有 110KB，
而且是从既有的 `geo/*.geojson` 压缩而来 —— 一份数据两处用（详情页的 SVG 轮廓 / 地球的球面线条）。

**② three.js 懒加载。**

`three.min.js` 670KB，若在首屏加载会把首屏时间拖到 3 秒以上。所以用
`IntersectionObserver` 监听地球区块，**滚到才加载**（提前 220px 预取）。首屏完全不受影响。

加载源优先华为云 OBS（国内 0.3 秒级），失败回退仓库相对路径。

**③ 球面插值细分。**

两个相邻经纬度点直接连直线，是球体的**弦**，会从球体内部穿过去 —— 视觉上线沉到球里。
所以每条边按 ≤2° 插值成折线（实测：欧洲到东亚一段 100° 的边细分成 116 个顶点，
模长恒等于半径，偏差 < 1e-15）。

**④ 点击拾取必须 worldToLocal。**

射线与球求交拿到的是**世界坐标**。球体被 `tilt`/`spin` 两层 Group 旋转过，直接拿世界坐标
反算经纬度会全错。必须先 `spin.worldToLocal()` 转回局部坐标。

这一条我做了离线验证：三个国家的中心点转过去后位置都是 `(0, 0, 1)` —— 精确正对相机。

### 投影与验证

经纬度 → 球面坐标（y 轴朝北，经度 0 落在 -Z 方向，即初始正对相机）：

```javascript
phi   = (90 - lat) * DEG
theta = (lon + 180) * DEG
x = -r * sin(phi) * cos(theta)
y =  r * cos(phi)
z =  r * sin(phi) * sin(theta)
```

反算与上式为严格逆运算，10 组测试（含南北极、日期变更线两侧）最大误差 **3.45e-12**。

把某国转到正对相机：`spin.rotation.y = -lon° - 90°`，`tilt.rotation.x = lat°`。

### 数据生成

```bash
python scripts/build_globe.py
```

读 `geo/{cn,fr,us}.geojson` 与 `geo/_ne_110m_land.geojson`，做三件事：

1. **Douglas-Peucker 抽稀**（容差 0.05°，球面上约 5.5km，肉眼无差别）
2. **标记跨日期变更线的断点**（"null" 分隔）—— 美国阿留申群岛相邻两点经度从 179 跳到 -179，
   直接连会是横贯全球的假线
3. **标签位置用最大环的包围盒中心**，不是全部顶点均值。实测差距很大：

   | 国家 | 全部顶点均值（错） | 最大环包围盒中心（对） |
   | --- | --- | --- |
   | 法国 | `[-7.2, 34.9]` 北非上空 | `[1.7, 46.7]` 法国本土 |
   | 美国 | `[-120.9, 48.4]` 加拿大西海岸 | `[-95.9, 37.3]` 堪萨斯一带 |

   原因是海外领地：法属圭亚那（-53°）、留尼汪（55°）、阿拉斯加（-150°）、夏威夷（-155°）
   会把均值拉出本土很远。

输出 `geo/globe.json` 110KB / 7496 顶点，球面渲染后 19180 顶点（一次 draw call）。

### 降级

| 情况 | 表现 |
| --- | --- |
| 浏览器不支持 WebGL | 提示「当前浏览器不支持 WebGL」，详情页的国界 SVG 仍可用 |
| three.js 两个源都不可达 | 提示「3D 模型未能加载」，其余功能不受影响 |
| globe.json 加载失败 | 同上，错误原因写在提示里 |
| 事件失败 | 不阻塞任何其他模块 —— 整个地球是独立闭环，坏了不影响卡片与检索 |

## 文档

| 文件 | 内容 |
| --- | --- |
| [`docs/算法调研.md`](docs/算法调研.md) | 检索算法、图文获取、实体消歧、TTS 四组对比；全部区分「本项目实测」与「第三方参考」 |

## 大模型使用（对应评分表「项目准备 · 大模型」）

DeepSeek `deepseek-flash`，**构建期调用**，六类真实任务。台账见 `logs/llm_calls.jsonl`。

### key 怎么管

key 只从环境变量 `DEEPSEEK_API_KEY` 读，`.env` 已在 `.gitignore` 里。

**页面永不接触 key。** 本站是静态托管且仓库公开，前端一旦出现 key 任何人按 F12 都能拿到，
爬虫几分钟内就会拿去刷额度。所以大模型调用全部发生在构建期——脚本调 API、结果写成 JSON、
页面只读 JSON。副作用是页面断网也能演示，正好满足录屏要求。

```bash
export DEEPSEEK_API_KEY=sk-xxx
python scripts/llm.py --selftest        # 连通性 + JSON 模式 + 翻译，三项自检
python scripts/llm_tasks.py --run all   # 三国跑四类任务（默认只预览）
python scripts/llm_tasks.py --run all --apply   # 确认后写回 data/*.json
python scripts/llm.py --stats           # 调用台账：次数 / 场景 / token / 花费
```

### 六类任务

| # | 场景 | 输入 | 产物 | 为什么非它不可 |
| --- | --- | --- | --- | --- |
| 1 | 实体消歧 | 中文名 + Wikidata 候选条目 | 选中的 QID + 排除理由 | 中文译名撞车：搜「圣米歇尔山」命中摩泽尔省的市镇 |
| 2 | 特征抽取 | 摘要 + 民俗文本 | `custom_facets` 六类标签，每条带原文依据 | 「世俗性 laïcité」这类概念，关键词规则抽不出 |
| 3 | 摘要精炼 | 百科导语 + 民俗文本 | 240~420 字地理文化段落 | 采集时按字数硬切，可能断在半句；且需统一口径 |
| 4 | 图注生成 | Commons 英文文件名 | 中文图注 | 250 国 × 2~4 张图，人工写上千条不现实 |
| 5 | 数据质检 | 整条档案 | `llm_audit`：问题清单 + 结论 | CI 只能查格式，查不出「首都写成上海」 |
| 6 | 知识库 QA | 整条档案 | 每国 6~8 组问答对 → 前端 2-gram + BM25 检索 | 知识库的落地 |

第 1 类就是评分表说的「融合」，第 2 类就是「特征提取」。

### 两个实测坑

**① thinking 默认开启，reasoning_tokens 会吃掉 max_tokens。**

同一句翻译，`max_tokens=64` 时推理吃掉全部 64 个，`content` 返回**空串**
（`finish_reason=length`）；关闭思考后只花 7 个 token 就给结果。

所以 `llm.py` 默认 `thinking=False`。抽取/翻译/质检不需要长链条推理，关掉既省钱又快 20 倍。
空响应会被显式抛错，不会静默写进 JSON（那是最难查的一类 bug）。

**② DeepSeek 没有 embedding 接口。**

定价页只有对话模型，调 `/embeddings` 会失败。所以「知识库」不走稠密向量路线，改为
**LLM 抽实体与标签 + BM25 稀疏检索**：零额外依赖、零第二个 key、可离线。
250 条以内的语料上稀疏检索的召回并不逊于向量检索，这个取舍会写进报告的算法比较。

### 第 6 类：知识库检索怎么落地

前端有一个「用一句话找国家」的搜索框，**检索在浏览器里算，不调 API**：

| 环节 | 在哪 | 做什么 |
| --- | --- | --- |
| 生成 | 构建期（DeepSeek） | 每国 6~8 组问答对，写入 `data/{iso}.json` 的 `knowledge_qa` |
| 建索引 | 构建期（`build_search_index.py`） | 合并成 `data/search.json`，25 条文档 / 13KB |
| 检索 | 浏览器（纯 JS） | 中文 2-gram 切分 + BM25 打分，零依赖、断网可用 |

为什么不用「每次提问都调大模型」：key 进浏览器就是泄露，而且几十条文档的检索
本地算比一次网络往返快两个数量级，还能断网演示。

两个细节决定它可不可用：

**① 停用词。** 中文 2-gram 会把「哪里能看」切成「哪里／里能／能看」，这些碎片在多个
文档里都出现，是纯噪声。实测未加停用词时，「哪里能看长城」会把「法国面积有多大？
首都是哪里？」顶到第二名——只因为含「哪里」。

**② 阈值。** 绝对阈值 1.5 + 相对阈值（最高分的 35%）。没有阈值时「日本有什么」会
返回 5 条 1.7 分的垃圾。加阈值后它能明确回答「没有」，这是检索系统该有的诚实。

实测 14 条查询：

```
「哪里能看长城」→ 中国×3（长城是什么时候建的 3.2 / 看地标 2.3 / 简介 2.1）
「说什么语言」  → 美国 6.2 / 中国 4.6 / 法国 3.9
「面积多大」    → 中国 9.0 / 美国 6.8 / 法国 5.2
「奶酪」        → 法国饮食制度 2.8
「世俗性」      → 法国文化特色 5.5
「极光」        → 无结果（数据集没有这个信息）
「日本有什么」  → 无结果（数据集只覆盖 3 国）
```

### 质检到底有效吗

一个只会输出 pass 的检查器毫无价值。所以做了注入测试：

```bash
python scripts/llm_tasks.py --audit-injection CN
```

把真数据改成四个确定错误（首都=上海、语言=法语、图注=自由女神像、坐标=悉尼），
要求至少检出 3 项且结论非 pass。实测检出 5 条（含一条额外发现：摘要仍写「首都北京」
与 capital 字段矛盾），结论 `fail`。**真实数据 pass 才因此可信。**

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

保存完后跑一次门禁，CI 里也是同一条命令：

```bash
python scripts/check_data.py     # 字段齐全 / 素材存在 / 几何合法 / 中国版图含台港澳 / index 与档案一致
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

