# -*- coding: utf-8 -*-
"""GitHub Contents API 薄封装 —— 支持中文路径、幂等写入、二进制上传。

设计目标
================================================================
1. **不依赖 git**：某些网络环境下 git 走代理访问 github.com 的 CONNECT
   隧道会被拦（502 / TLS 握手失败），而 api.github.com 通道正常，
   故提供基于 Contents API 的等价能力。
2. **令牌零明文**：只从环境变量读取，绝不写入文件、日志或异常信息。
   未设置时返回 BLOCKED，不抛 KeyError。
3. **中文文件名**：路径必须 URL 编码，否则请求直接失败且错误体为空。
4. **幂等**：已有文件走更新（带 sha），无则新建，可重复执行。

环境变量
================================================================
    XIAOGANG_TOKEN   必需，GitHub PAT（需 repo / public_repo scope）

用法
================================================================
    from gh_api import GitHub
    gh = GitHub(repo="OWNER/REPO", branch="main")   # 令牌自动读环境变量
    gh.put("docs/notes.md", "# hello")
    gh.put("img/logo.png", open("logo.png", "rb").read())

命令行自检
================================================================
    python gh_api.py            # 只报连接与权限，不打印令牌
"""
import os
import json
import time
import base64
import urllib.request
from urllib.parse import quote

TOKEN_ENV = "XIAOGANG_TOKEN"
API_ROOT = "https://api.github.com"


def _enc_url(url):
    """只对 path 部分做 URL 编码，保留 scheme 与 / 分隔符。

    注意 safe="/~" 不能省——否则整个 path 会被压成一段。
    """
    head, sep, rest = url.partition("://")
    parts = rest.split("/", 1)
    if len(parts) == 1:
        return url
    return head + sep + parts[0] + "/" + quote(parts[1], safe="/~")


class GitHub(object):
    """GitHub Contents API 客户端。

    令牌从环境变量 TOKEN_ENV 读取，**任何情况下都不会出现在返回值里**。
    """

    def __init__(self, repo, branch="main", token=None, timeout=60):
        self.repo = repo
        self.branch = branch
        self.api = "%s/repos/%s" % (API_ROOT, repo)
        # token 参数仅为测试便利；生产一律走环境变量
        self._tok = token or os.environ.get(TOKEN_ENV)
        self.timeout = timeout
        self.hdr = {
            "User-Agent": "sinoport-sync",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
        if self._tok:
            self.hdr["Authorization"] = "Bearer " + self._tok

    # ---------------------------------------------------------- 底层
    def _call(self, path, method="GET", data=None, retries=3):
        """发起请求。瞬时网络错误自动退避重试。

        本机走代理访问 api.github.com 时偶发 RemoteDisconnected /
        超时，重试即可成功 —— 故对幂等的读写都加重试。
        """
        last = ("ERR", "")
        for attempt in range(retries):
            base, _, tail = (self.api + path).partition("?")
            url = _enc_url(base) + (("?" + tail) if tail else "")
            body = json.dumps(data).encode() if data is not None else None
            req = urllib.request.Request(url, data=body, method=method,
                                         headers=self.hdr)
            try:
                r = urllib.request.urlopen(req, timeout=self.timeout)
                return r.status, r.read().decode("utf-8", "replace")
            except Exception as e:
                b = ""
                try:
                    b = e.read().decode("utf-8", "replace")
                except Exception:
                    pass
                code = getattr(e, "code", None)
                last = (code or "ERR", b)
                # HTTP 层错误（4xx/5xx）重试无意义，直接返回
                if code is not None:
                    return last
                time.sleep(1.0 * (attempt + 1))
        return last

    # ---------------------------------------------------------- 查询
    def whoami(self):
        """返回 (status, login)。令牌无效时 login 为空串。"""
        s, b = self._call_url(API_ROOT + "/user")
        if s != 200:
            return s, ""
        try:
            return s, json.loads(b)["login"]
        except Exception:
            return s, ""

    def _call_url(self, url, method="GET", data=None):
        base, _, tail = url.partition("?")
        u = _enc_url(base) + (("?" + tail) if tail else "")
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(u, data=body, method=method,
                                     headers=self.hdr)
        try:
            r = urllib.request.urlopen(req, timeout=self.timeout)
            return r.status, r.read().decode("utf-8", "replace")
        except Exception as e:
            b = ""
            try:
                b = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            return getattr(e, "code", "ERR"), b

    def sha_of(self, path):
        """返回文件 blob sha；不存在返回 None。"""
        s, b = self._call("/contents/%s?ref=%s" % (path, self.branch))
        if s == 200:
            try:
                return json.loads(b)["sha"]
            except Exception:
                return None
        return None

    def listdir(self, path=""):
        """列目录；失败返回空列表。"""
        q = "?ref=%s" % self.branch if path else "?ref=%s" % self.branch
        s, b = self._call("/contents/%s%s" % (path, q))
        if s != 200:
            return []
        try:
            return json.loads(b)
        except Exception:
            return []

    # ---------------------------------------------------------- 写入
    def put(self, path, raw, message=None):
        """写入文件（幂等）。raw 为 str 或 bytes。

        返回 (ok, info)。ok 为 False 时 info 是错误摘要。
        """
        if not self._tok:
            return False, "[BLOCKED] 未设置环境变量 %s" % TOKEN_ENV
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        cur = self.sha_of(path)
        msg = message or ("chore: update %s" % path if cur
                          else "feat: add %s" % path)
        payload = {
            "message": msg,
            "content": base64.b64encode(raw).decode(),
            "branch": self.branch,
        }
        if cur:
            payload["sha"] = cur
        s, b = self._call("/contents/%s" % path, "PUT", payload)
        if s in (200, 201):
            try:
                return True, json.loads(b)["content"]["sha"][:10]
            except Exception:
                return True, "%d bytes" % len(raw)
        return False, (b or str(s))[:200]

    def put_text(self, path, text, message=None):
        return self.put(path, text, message)

    def put_bytes(self, path, raw, message=None):
        return self.put(path, raw, message)


if __name__ == "__main__":
    # 自检：只报状态，不打印令牌
    tok = os.environ.get(TOKEN_ENV)
    if not tok:
        print("[BLOCKED] 未设置环境变量 %s" % TOKEN_ENV)
        print("示例：set %s=<your GitHub PAT>" % TOKEN_ENV)
        raise SystemExit(2)
    print("环境变量 %s : 已设置（长度 %d，不显示内容）" % (TOKEN_ENV, len(tok)))
    g = GitHub("SINOSHOP-OPEN/SINOSHOP-Platform")
    s, login = g.whoami()
    print("API 连接     : %s" % ("OK, login=%s" % login if s == 200
                                   else "FAIL %s" % s))
    print("目标仓库     : %s@%s" % (g.repo, g.branch))
    print("scripts/ 内容:")
    for f in g.listdir("scripts"):
        print("   %-24s %s bytes" % (f.get("name"), f.get("size")))
