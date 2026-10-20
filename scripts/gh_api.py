# -*- coding: utf-8 -*-
"""Gitee -> GitHub 内容同步（SinoPORT 仓库）。

原因：本机 git 走代理访问 github.com 的 CONNECT 隧道被拦（502），
      但 api.github.com 通道可用，故改用 Contents API 逐文件写入。
令牌取自环境变量 XIAOGANG_TOKEN，明文不落盘。
"""
import os
import json
import base64
import urllib.request
from urllib.parse import quote


def _enc_path(url):
    """只编码 path 部分，保留 https:// 与 / 分隔符。"""
    head, sep, rest = url.partition("://")
    parts = rest.split("/", 1)
    if len(parts) == 1:
        return url
    return head + sep + parts[0] + "/" + quote(parts[1], safe="/~")

TOK = os.environ["XIAOGANG_TOKEN"]
REPO = "SINOSHOP-OPEN/SinoPORT"
API = "https://api.github.com/repos/%s" % REPO
BRANCH = "main"
HDR = {
    "User-Agent": "py",
    "Accept": "application/vnd.github+json",
    "Authorization": "Bearer " + TOK,
    "Content-Type": "application/json",
}


def gh(path, method="GET", data=None):
    # 传入相对路径时拼上 API 前缀；随后统一做 URL 编码
    url = path if path.startswith("http") else API + path
    base, _, tail = url.partition("?")
    url = _enc_path(base) + (("?" + tail) if tail else "")
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=HDR)
    try:
        resp = urllib.request.urlopen(req, timeout=40)
        return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as e:
        b = ""
        try:
            b = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return getattr(e, "code", "ERR"), b


def sha_of(path):
    s, b = gh("/contents/%s?ref=%s" % (path, BRANCH))
    if s == 200:
        return json.loads(b)["sha"]
    return None


def put(path, content):
    """写入单个文件：有 sha 则更新，否则新建。"""
    cur = sha_of(path)
    payload = {
        "message": "docs: sync from Gitee master (V6.4 + eco-channel 3.27x)" if cur
                   else "feat: initial sync from Gitee master (V6.4)",
        "content": base64.b64encode(content.encode("utf-8")).decode(),
        "branch": BRANCH,
    }
    if cur:
        payload["sha"] = cur
    s, b = gh("/contents/%s" % path, "PUT", payload)
    if s in (200, 201):
        return True, json.loads(b)["content"]["sha"][:10]
    return False, b[:200]


def upload_blob(path, local):
    """二进制文件（PNG）。"""
    with open(local, "rb") as f:
        raw = f.read()
    cur = sha_of(path)
    payload = {
        "message": "docs: add screenshots" if cur else "feat: add screenshots",
        "content": base64.b64encode(raw).decode(),
        "branch": BRANCH,
    }
    if cur:
        payload["sha"] = cur
    s, b = gh("/contents/%s" % path, "PUT", payload)
    if s in (200, 201):
        return True, "%d bytes" % len(raw)
    return False, b[:200]


if __name__ == "__main__":
    print("module ready")
