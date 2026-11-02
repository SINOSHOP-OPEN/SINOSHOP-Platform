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
import argparse

# 复用 gh_api：令牌读取、URL 编码、幂等 PUT 全部收敛在一处。
# 这样令牌只在 gh_api 里从环境变量读一次，本文件不接触任何凭据。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gh_api import GitHub, TOKEN_ENV   # noqa: E402


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
    if not src:
        print("[BLOCKED] 未指定源目录：--src 或环境变量 SINOPORT_SRC")
        return 2
    if not os.environ.get(TOKEN_ENV):
        print("[BLOCKED] 未找到环境变量 %s" % TOKEN_ENV)
        return 2
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        print("[BLOCKED] 源目录不存在：%s" % src)
        return 2

    gh = GitHub(repo=args.repo, branch=args.branch)
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
