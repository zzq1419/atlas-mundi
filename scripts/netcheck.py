#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""找到本机可用的 HTTP 代理，并把它设进环境变量。

为什么必须有这个
----------------
`urllib` 只认 `HTTP_PROXY / HTTPS_PROXY` 环境变量，**不读 Windows 的"系统代理"设置**。
而 Clash / v2rayN / Shadowsocks 改的恰恰是系统代理（注册表里的 ProxyEnable + ProxyServer），
命令行窗口里并没有那几条环境变量。

结果就是：浏览器能打开维基百科，脚本却一律连接失败 —— 这不是"代理没开"，
而是 Python 根本不知道代理在哪。2026-10-28 那次"五国全失败"就是这个原因
（叠加一个 cp936 打印崩溃），排查时很容易误判成网络或反爬。

探测顺序
--------
1. 调用方显式传入的 --proxy
2. 环境变量 HTTPS_PROXY / HTTP_PROXY
3. Windows 注册表里的系统代理
4. 常见本地端口（Clash 7897/7890、v2rayN 10809/10808、通用 1080/8080…）

**每个候选都要真的抓一次维基才算数**：端口开着但节点没连上的情况非常常见，
只看端口会得到一个"看起来能用其实不通"的代理，比没有更糟。

用法
----
    from netcheck import detect, apply
    proxy, source = detect()      # 探测（会打印结果）
    apply(proxy)                  # 设进 os.environ，之后所有 urllib 请求都走它
"""

from __future__ import annotations

import os
import socket
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

UA = "AtlasMundi/0.3 (course project; contact: 2036829270@qq.com)"

# 用一个"必然存在且很小"的实体做探针（Q17 = 日本，只取 labels）
PROBE = ("https://www.wikidata.org/w/api.php"
         "?action=wbgetentities&ids=Q17&props=labels&format=json")

# 常见本地代理端口，按使用频率排
PORTS = [7897, 7890, 10809, 10808, 1080, 8080, 8888, 2080, 7891, 8889, 9090]


def _from_env():
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v, "环境变量 " + k
    return None, ""


def _from_registry():
    """读 Windows 系统代理。ProxyServer 可能是 127.0.0.1:7897 或 http=..;https=.."""
    if os.name != "nt":
        return None, ""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        try:
            enable = winreg.QueryValueEx(key, "ProxyEnable")[0]
        except FileNotFoundError:
            return None, ""
        if not enable:
            return None, ""
        try:
            server = winreg.QueryValueEx(key, "ProxyServer")[0]
        except FileNotFoundError:
            return None, ""
        if not server:
            return None, ""
        if "=" in server:                     # http=1.2.3.4:8080;https=...
            parts = {}
            for seg in server.split(";"):
                if "=" in seg:
                    k, v = seg.split("=", 1)
                    parts[k.strip().lower()] = v.strip()
            server = parts.get("https") or parts.get("http") or ""
        if not server:
            return None, ""
        url = server if "://" in server else "http://" + server
        return url, "Windows 系统代理"
    except Exception:
        return None, ""


def _open_port(port, host="127.0.0.1", timeout=0.35):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def works(proxy, timeout=8):
    """通过 proxy 抓一次维基。能不能用只有试了才知道。"""
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    op = urllib.request.build_opener(handler)
    req = urllib.request.Request(PROBE, headers={
        "User-Agent": UA, "Accept": "application/json"})
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        # 403/429 说明代理链路是通的（维基在回话），也算能用
        return e.code in (403, 429)
    except Exception:
        return False


def detect(explicit=None, verbose=True, timeout=8):
    """返回 (proxy 或 None, 来源说明)。不修改 os.environ。"""
    tried = []
    cands = []
    if explicit:
        cands.append((explicit, "--proxy 参数"))
    env, env_src = _from_env()
    if env:
        cands.append((env, env_src))
    sr, sr_src = _from_registry()
    if sr:
        cands.append((sr, sr_src))
    for p in PORTS:
        if _open_port(p):
            cands.append(("http://127.0.0.1:%d" % p, "本地端口 %d" % p))

    seen = set()
    for url, src in cands:
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        ok = works(url, timeout=timeout)
        tried.append((url, src, ok))
        if ok:
            if verbose:
                print("  代理：%s（%s）可用" % (url, src))
            return url, src
    if verbose:
        if tried:
            print("  代理：试过 %d 个都不通 —— %s"
                  % (len(tried), "，".join("%s(%s)" % (u, s) for u, s, _ in tried)))
        else:
            print("  代理：没找到（环境变量、系统代理、常见端口都没有）")
    return None, ""


def apply(proxy):
    """把代理设进环境变量，之后本进程和子进程的 urllib 都会走它。"""
    if not proxy:
        return
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ[k] = proxy
    # 本机回环不要走代理（OBS/本地服务器调试会用）
    os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")


_CACHE = {"done": False, "proxy": None, "src": "", "explicit": None}


def setup(explicit=None, verbose=True):
    """探测 + 应用，返回 (proxy, source)。同参数重复调用只探测一次。"""
    if _CACHE["done"] and explicit is None and _CACHE["explicit"] is None:
        if verbose:
            print("  代理：%s（%s，已探测过）"
                  % (_CACHE["proxy"], _CACHE["src"]) if _CACHE["proxy"] else
                  "  代理：未找到（已探测过）")
        return _CACHE["proxy"], _CACHE["src"]
    proxy, src = detect(explicit=explicit, verbose=verbose)
    apply(proxy)
    _CACHE.update(done=True, proxy=proxy, src=src, explicit=explicit)
    return proxy, src


def setup_once():
    """给"被别的脚本 import 的模块"用：import 时就把代理准备好，不再重复打印。"""
    if _CACHE["done"]:
        return
    setup(verbose=False)
