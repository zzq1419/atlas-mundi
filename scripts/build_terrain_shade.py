# -*- coding: utf-8 -*-
"""从 assets/tex/elev.png 生成地形山体阴影（hillshade）。

    python scripts/build_terrain_shade.py

生成后记得把 assets/tex/terrain-shade.webp 的 md5 前 8 位写进 index.html 的
TEX_VER（scripts/stamp_tex_ver.py 会自动刷）。

elev.png 的编码（前端 probeElevAt 已用同一套）：
    h = R*256 + G - 32768   （单位：米）

输出 assets/tex/terrain-shade.webp：2048x1024 灰度
    · 陆地：标准 GIS hillshade（方位 315°、高度角 45°），0..1
    · 海洋：0.5（中性，叠加时不变亮也不变暗）
shader 里按 col *= 0.55 + 0.9 * hs 使用，hs=0.5 恰好等于 1.0。
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

# --- 极区 cos(lat) → 0，梯度会炸成条纹；按纬度把强度收掉 ---
latk = np.clip((np.abs(np.linspace(90, -90, H)) - 60.0) / 25.0, 0.0, 1.0)[:, None]
hs = hs * (1.0 - latk) + 0.5 * latk

out = Image.fromarray((np.clip(hs, 0, 1) * 255).astype(np.uint8), 'L')
out.save(DST, format='WEBP', quality=92, method=6)
print('size', out.size, 'mode', out.mode, 'bytes', os.path.getsize(DST))
print('hs min/mean/max %.3f %.3f %.3f' % (hs.min(), hs.mean(), hs.max()))
land = hs[~sea]
print('land hs p1/p10/p50/p90/p99: %.3f %.3f %.3f %.3f %.3f' % tuple(
    np.percentile(land, [1, 10, 50, 90, 99])))
