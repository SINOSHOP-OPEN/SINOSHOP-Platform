# -*- coding: utf-8 -*-
"""SinoPORT — Gitee -> GitHub 仓库同步工具

用途
================================================================
把 Gitee 上SINOPORT 仓库 master 分支的内容，同步到 GitHub 对应仓库。
之所以需要本工具：本机 git 走代理访问 github.com 的 CONNECT 隧道会被拦
（502/ TLS 握手失败），而 api.github.com 通道正常，故改用 Contents API
逐文件写入。

为什么不用 git push
----------------------------------------------------------------
    $ git clone https://github.com/OWNER/REPO.git
    fatal: unable to access ...: schannel: failed to receive handshake
    # 换 HTTP/1.1 / 关 sslVerify 均无效，仍CONNECT tunnel failed, 502

用法
================================================================
    set XIAOGANG_TOKEN=<你的 GitHub PAT>       # Windows
    export XIAOGANG_TOKEN=<你的 GitHub PAT>   # macOS / Linux

    python sync_sinoport.py ^
        --src   D:\path\to\SinoPORT_参赛版 ^
        --repo  SINOSHOP-OPEN/SinoPORT ^
        --branch main

    # 或用环境变量指定源目录
    set SINOPORT_SRC=D:\path\to\SinoPORT_参赛版
    python sync_sinoport.py --repo SINOSHOP-OPEN/SinoPORT

安全性
================================================================
令牌**只从环境变量读取，不写入任何文件、不打印**。
脚本不包含任何硬编码路径与凭据，可安全入库。

已实测（2026-10-20）
----------------------------------------------------------------
    33 项同步 -> 成功 33 / 失败 0 / 缺失 0
"""
import os
import sys
import json
import base64
import argparse
import urllib.request
from urllib.parse import quote

# ---------------------------------------------------------------- API 通道

HDR = {
    "User-Agent": "sinoport-sync",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
}


def make_api(token):
    hdr = dict(HDR)
    hdr["Authorization"] = "Bearer " + token
    return hdr


def enc_url(url):
    """只对 path 部分做 URL 编码；保留 scheme 与 / 分隔符。

    中文文件名必须编码，否则请求直接失败（且错误体为空）。
    """
    head, sep, rest = url.partition("://")
    parts = rest.split("/", 1)
    if len(parts) == 1:
        return url
    return head + sep + parts[0] + "/" + quote(parts[1], safe="/~")


class GitHub(object):
    def __init__(self, token, repo, branch="main"):
        self.api = "https://api.github.com/repos/%s" % repo
        self.branch = branch
        self.hdr = make_api(token)

    def _call(self, path, method="GET", data=None):
        url = self.api + path
        base, _, tail = url.partition("?")
        url = enc_url(base) + (("?" + tail) if tail else "")
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method,
                                     headers=self.hdr)
        try:
            r = urllib.request.urlopen(req, timeout=60)
            return r.status, r.read().decode("utf-8", "replace")
        except Exception as e:
            b = ""
            try:
                b = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            return getattr(e, "code", "ERR"), b

    def sha_of(self, path):
        s, b = self._call("/contents/%s?ref=%s" % (path, self.branch))
        return json.loads(b)["sha"] if s == 200 else None

    def put(self, path, raw, msg):
        """raw为bytes。已有文件则更新，否则新建。"""
        cur = self.sha_of(path)
        payload = {
            "message": msg,
            "content": base64.b64encode(raw).decode(),
            "branch": self.branch,
        }
        if cur:
            payload["sha"] = cur
        s, b = self._call("/contents/%s" % path, "PUT", payload)
        if s in (200, 201):
            return True, json.loads(b)["content"]["sha"][:10]
        return False, b[:200]


# ---------------------------------------------------------------- 同步清单

TEXT_FILES = [
    "README.md", "README.en.md", "README-V1.0.md", "LICENSE",
    "requirements.txt", ".gitignore", "CONTRIBUTING.md", "DEPENDENCIES.md",
    "demo.py", "demo_evolution.py",
    "run_filming.bat", "rec_screen.bat",
    "src/core/raster_core.py",
    "src/model/build_pyramid_r6.py", "src/model/film_engine.py",
    "src/model/probe_conn_fix.py",
    "src/specs/pyramid_spec_r6.py", "src/specs/bw_geometry.py",
    "src/specs/berths_spec_r2.py", "src/specs/shore_spec_r2.py",
    "src/specs/next_films_spec_r2.py",
    "src/verify/verify_frames.py",
    "docs/standards/SINOPORT-GEO-COD-26-001-V6.4.md",
    "docs/reports/PYRAMID_HOLES_R6_20261019.json",
    "docs/reports/BERTHS_SPEC_R2_20261018.json",
    "docs/reports/BUILD_PYRAMID_R6_20261019.json",
    "docs/reports/CONN_FACTS_20261017.json",
]

# 目录同步（中文文件名在此列出）
DOC_DIRS = {
    "docs/papers": ["SINOPORT_作品介绍文档_赛道二版v1_20261019.md",
                    "SINOPORT_同类方案对比表_20261019.md"],
    "docs/issues": ["ISSUE-001-生态鱼道升级集成结构.md",
                    "PR-001-生态鱼道集成重构.md"],
}

BIN_FILES = [
    "docs/reports/SCREENSHOT_demo_py_4of4_PASS.png",
    "docs/reports/SCREENSHOT_demo_evolution.png",
]


def main():
    ap = argparse.ArgumentParser(description="SinoPORT 仓库同步工具")
    ap.add_argument("--src", help="本地源目录（也可用环境变量 SINOPORT_SRC）")
    ap.add_argument("--repo", default="SINOSHOP-OPEN/SinoPORT")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()

    src = args.src or os.environ.get("SINOPORT_SRC")
    tok = os.environ.get("XIAOGANG_TOKEN")
    if not src:
        print("[BLOCKED] 未指定源目录：--src 或环境变量 SINOPORT_SRC")
        return 2
    if not tok:
        print("[BLOCKED] 未找到环境变量 XIAOGANG_TOKEN")
        return 2
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        print("[BLOCKED] 源目录不存在：%s" % src)
        return 2

    gh = GitHub(tok, args.repo, args.branch)
    print("源目录 : %s" % src)
    print("目标   : %s@%s" % (args.repo, args.branch))
    print()

    jobs = [(p, p) for p in TEXT_FILES]
    for d, names in DOC_DIRS.items():
        jobs += [(d + "/" + n, d + "/" + n) for n in names]
    ok = bad = miss = 0
    fails = []

    for remote, local in jobs:
        lp = os.path.join(src, local.replace("/", os.sep))
        if not os.path.isfile(lp):
            print("  [MISS] %s" % remote)
            miss += 1
            continue
        raw = open(lp, "rb").read()
        good, info = gh.put(remote, raw,
                            "docs: sync from Gitee master (V6.4, eco-channel 3.27x)")
        print("  [%s] %-56s %s" % ("OK" if good else "FAIL", remote[:56], info))
        ok += good
        bad += (not good)
        if not good:
            fails.append(remote)

    print()
    print("=== 二进制 ===")
    for rel in BIN_FILES:
        lp = os.path.join(src, rel.replace("/", os.sep))
        if not os.path.isfile(lp):
            print("  [MISS] %s" % rel)
            miss += 1
            continue
        raw = open(lp, "rb").read()
        good, info = gh.put(rel, raw, "docs: add terminal screenshots")
        print("  [%s] %-56s %s" % ("OK" if good else "FAIL", rel[:56], info))
        ok += good
        bad += (not good)
        if not good:
            fails.append(rel)

    print()
    print("=== 汇总：成功 %d，失败 %d，缺失 %d ===" % (ok, bad, miss))
    if fails:
        print("失败清单:", fails)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
