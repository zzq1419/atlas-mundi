# -*- coding: utf-8 -*-
"""从 assets/tex/elev.png 生成地形山体阴影（hillshade）。

    python scripts/build_terrain_shade.py

生成后记得把 assets/tex/terrain-shade.webp 的 md5 前 8 位写进 index.html 的
TEX_VER（scripts/stamp_tex_ver.py 会自动刷）。

elev.png 的编码（前端 probeElevAt 已用同一套）：
    h = R*256 + G - 32768   （单位：米）

输出 assets/tex/terrain-shade.webp：2048x1024 灰度
    · 陆地：标准 GIS hillshade（方位 315°、高度角 45°）+ 大尺度地势项（TPI），0..1
    · 海洋：0.5（中性，叠加时不变亮也不变暗）
shader 里按 col *= 0.10 + 1.64 * hs 使用（中性点 0.55）。
"""
import os
import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'assets', 'tex', 'elev.png')
DST = os.path.join(ROOT, 'assets', 'tex', 'terrain-shade.webp')

im = Image.open(SRC).convert('RGB')
W, H = im.size
a = np.asarray(im).astype(np.float32)
h = a[:, :, 0] * 256.0 + a[:, :, 1] - 32768.0     # 米

# --- 轻微平滑：2048 分辨率本身带噪，山影会把噪点放大成"麻点" ---
him = Image.fromarray(np.clip((h + 8000) / 16000 * 255, 0, 255).astype(np.uint8))
him = him.filter(ImageFilter.GaussianBlur(1.5))
h = np.asarray(him).astype(np.float32) / 255 * 16000 - 8000

# --- 坡度 / 坡向（等距柱状投影要做纬度余弦校正）---
lat = np.linspace(90, -90, H, dtype=np.float32)[:, None] * np.pi / 180.0
dy_m = 110540.0 * (180.0 / H)                      # 每像素南北向米数
dx_m = 111320.0 * np.cos(lat) * (360.0 / W)         # 每像素东西向米数（随纬度收缩，极区接近 0）
dx_m = np.maximum(dx_m, 1.0)

gy, gx = np.gradient(h)
gx = gx / dx_m
gy = -gy / dy_m                                    # 行索引向下 = 向南，取反成"向北为正"

# 垂直夸张：2048 分辨率把真实山坡平均掉了（相邻像素跨 20km，高差只有几十米），
# 原始坡度算出来的山影几乎是平的。地形可视化本来就允许夸张，这里放大 12 倍。
EXAG = 9.0
gx *= EXAG
gy *= EXAG

slope = np.arctan(np.hypot(gx, gy))                # 0=平地
aspect = np.arctan2(gx, gy)                        # 从北顺时针，弧度

az = np.radians(315.0)                             # 光源方位：西北
zen = np.radians(45.0)                             # 高度角 45°

hs = (np.cos(zen) * np.cos(slope) +
      np.sin(zen) * np.sin(slope) * np.cos(az - aspect))
hs = np.clip(hs, 0.0, 1.0)

# --- 局部地势（TPI）：让"高"看起来真的是高的 ---
# 单方向 hillshade 只回答"这面坡朝哪边"，不回答"这儿比周围高还是低"。
# 塔里木盆地四周是山脊，山影把四边压暗、中间平坦处留亮 —— 整块就被读成
# 抬起来的台地；青藏高原则因为面积太大、光又偏西南，反而整片压暗像洼地。
# 这就是用户说的"盆地看上去是凸起、高原反而像盆地"。
# 用大半径（约 2400km）的局部均值差（TPI）给一层"绝对地势"：
#   比周围低（盆地、谷地）→ 压暗；比周围高（高原、山脊）→ 提亮。
def box_mean(arr, r):
    """半径 r 的方形窗口均值，走积分图，float64 防累加丢精度。"""
    a64 = np.pad(arr.astype(np.float64), r, mode='edge')
    ii = np.cumsum(np.cumsum(a64, axis=0), axis=1)
    ii = np.pad(ii, ((1, 0), (1, 0)))
    k = 2 * r + 1
    total = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
    return (total / (k * k)).astype(np.float32)

# 半径 40px ≈ 7° ≈ 770km：窗口刚好把盆地的边缘山地包进来，
# 盆地中心就会稳定落在 -1400~-1600m（半径 120px 时塔里木只剩 -113m，
# 因为窗口比盆地本身还大，均值和中心一样）。实测 r=40 时：
#   塔里木 -1623、四川盆地 -1371、青藏高原 +1440、喜马拉雅 +1399、华北平原 -512
TPI_R = 40
tpi = h - box_mean(h, TPI_R)
tpi_n = np.clip(tpi / 1600.0, -1.0, 1.0)     # ±1600m 归一化

# --- 海洋压成中性，深海不该有"山影" ---
sea = h < 0.0
hs[sea] = 0.5

# --- 陆地对齐到 0.5、并拉对比 ---
# 315° 是高纬陆地的主要迎光面，算出来的陆地整体偏亮（中位 0.69），
# 直接叠加等于给整块地图打了一层高光，反而看不出"坡"。
# 把陆地中位值压回 0.5（叠加时该处不变色），再放大 1.8 倍做明暗差。
land0 = hs[~sea]
med = float(np.median(land0))
hs[~sea] = np.clip(0.5 + (land0 - med) * 4.2, 0.0, 1.0)

# 叠加地势项：盆地/谷地压暗、高原/山脊提亮（在 0..1 的 hs 空间里）。
# 0.14 时数值上已经拉开（塔里木 0.36 / 青藏 0.63），但看屏幕还是分不出 ——
# 分层设色本身就"低地黄绿、山地深棕"，低地底色浅、山地底色深，
# 正好把这层明暗抵掉一半。所以一路加到 0.30，才压得住色带。
# 正负不对称：低洼要压得狠（要靠它把"盆地像台地"的错觉掰回来），
# 高处只轻轻提 —— 高原那片本来就是雪线以上的纯白，再提就糊成一片死白，
# 山脉细节全丢了（0.30 对称那版实测就是这样）。
_tn = tpi_n[~sea]
hs[~sea] = np.clip(hs[~sea] + 0.32 * np.clip(_tn, -1, 0)
                   + 0.11 * np.clip(_tn, 0, 1), 0.0, 1.0)

# --- 极区 cos(lat) → 0，梯度会炸成条纹；按纬度把强度收掉 ---
latk = np.clip((np.abs(np.linspace(90, -90, H)) - 60.0) / 25.0, 0.0, 1.0)[:, None]
hs = hs * (1.0 - latk) + 0.5 * latk

out = Image.fromarray((np.clip(hs, 0, 1) * 255).astype(np.uint8), 'L')
out.save(DST, format='WEBP', quality=92, method=6)

# ---------- 第二张：供顶点位移用的高程图 ----------
# 512 列就够：球体顶点是 512 段经向，再细也采不出更多信息；
# 8 位精度 = 9000/255 ≈ 35m 一级，换算到球半径上是 0.0002 —— 远小于一个像素。
# 海洋一律 0（不位移），否则马里亚纳海沟会把球压出一个坑。
ELEV_DST = os.path.join(ROOT, 'assets', 'tex', 'terrain-elev.webp')
# 存的是"位移系数"而不是海拔：0.5 = 球面本身（海平面就地取球面）。
#   陆地 0.5 + h/9000*0.5（珠峰 → 1.0）
#   海洋 固定 0.5
# 曾经试过让海底也往下走（真实高程），想消掉海岸那道台阶 —— 台阶确实没了，
# 但代价是整颗球"缩"了一圈，陆地的凸起被包在里面，反而更看不出来。
# 海岸线本身不跳：h≈0 的陆地就是 0.5，和海面天然接上，台阶只在深海，
# 而深海在球面上本来就看不见。
elev_n = np.where(h >= 0.0, 0.5 + 0.5 * h / 9000.0, 0.5)
elev_n = np.clip(elev_n, 0.0, 1.0)
eim = Image.fromarray((elev_n * 255).astype(np.uint8), 'L')
eim = eim.resize((1024, 512), Image.LANCZOS)
# 2.2 的模糊不是磨皮：海岸线那一圈高程从 0 直接跳到几百米，
# 顶点法线会在这个 1 像素的台阶上被拉成 90° —— 屏幕上就是一圈尖刺。
# 位移和法线都只用这张低通图，山脉细节交给山影图，各管一段。
eim = eim.filter(ImageFilter.GaussianBlur(2.6))
eim.save(ELEV_DST, format='WEBP', quality=95, method=6)
print('elev-map', eim.size, 'bytes', os.path.getsize(ELEV_DST))
print('size', out.size, 'mode', out.mode, 'bytes', os.path.getsize(DST))
print('hs min/mean/max %.3f %.3f %.3f' % (hs.min(), hs.mean(), hs.max()))
land = hs[~sea]
print('land hs p1/p10/p50/p90/p99: %.3f %.3f %.3f %.3f %.3f' % tuple(
    np.percentile(land, [1, 10, 50, 90, 99])))

# 抽查：盆地应当明显比高原暗
def at(lon, lat):
    x = int((lon + 180) / 360 * W); y = int((90 - lat) / 180 * H)
    return hs[y, x]
for k, (lo, la) in {'塔里木盆地': (83, 39), '四川盆地': (105, 30),
                    '青藏高原': (88, 33), '黄土高原': (108, 36),
                    '华北平原': (116, 37)}.items():
    print('  %s hs=%.3f tpi=%+.0fm' % (k, at(lo, la),
          tpi[int((90 - la) / 180 * H), int((lo + 180) / 360 * W)]))
