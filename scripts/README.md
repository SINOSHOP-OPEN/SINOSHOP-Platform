# scripts/ — SinoPORT 仓库同步工具

把 **Gitee → GitHub** 的仓库内容同步自动化，避免手工搬运。

## 为什么需要这个工具

本机 git 访问 GitHub 受阻：

```
$ git clone https://github.com/OWNER/REPO.git
fatal: unable to access '...': schannel: failed to receive handshake, SSL/TLS connection failed

# 换 HTTP/1.1、关 sslVerify 均无效
fatal: unable to access '...': CONNECT tunnel failed, response 502
```

而 **api.github.com 通道正常**（`github.com` 与 `api.github.com` 用
Python `urllib` 均可直连）。因此本工具改用 **GitHub Contents API**
逐文件写入，功能等价且更可控：

- 有 `sha` 则更新，无则新建 → **幂等，可重复执行**
- 无需本地克隆，不受 TLS 层影响
- 令牌只从环境变量读，**不写入任何文件**

## 文件

| 文件 | 作用 |
|---|---|
| `gh_api.py` | GitHub Contents API 薄封装（URL 编码 / 幂等 PUT / 二进制上传） |
| `sync_sinoport.py` | SinoPORT 仓库同步主程序（33 个文件的清单） |

## 前置要求

1. **Python 3.8+**（标准库即可，无需 `pip install`）
2. 一个 GitHub PAT，需要 `repo`（或public_repo）scope

## 设置令牌

**令牌只从环境变量读取，不写入任何文件、不打印。**

```bat
:: Windows CMD
set XIAOGANG_TOKEN=ghp_xxxxxxxxxxxx

:: Windows PowerShell
$env:XIAOGANG_TOKEN = "ghp_xxxxxxxxxxxx"
```

```bash
# macOS / Linux
export XIAOGANG_TOKEN=ghp_xxxxxxxxxxxx
```

## 使用

```bash
python sync_sinoport.py \
    --src   /path/to/SinoPORT参赛版 \
    --repo  SINOSHOP-OPEN/SinoPORT \
    --branch main
```

源目录也可用环境变量指定：

```bash
export SINOPORT_SRC=/path/to/SinoPORT参赛版
python sync_sinoport.py --repo SINOSHOP-OPEN/SinoPORT
```

## 输出示例

```
源目录 : /path/to/SinoPORT参赛版
目标   : SINOSHOP-OPEN/SinoPORT@main

  [OK] README.en.md                    0b99b6a608
  [OK] demo.py                         9ec62a2005
  ...
  [OK] docs/reports/SCREENSHOT_demo_py_4of4_PASS.png   203823 bytes

=== 汇总：成功 33，失败 0，缺失 0 ===
```

任一文件 FAIL 时脚本返回非零退出码，便于 CI 集成。

## 已知坑（已在本工具中修复）

**中文文件名的 URL 编码**：不编码时请求直接失败，且 GitHub 返回的
错误体为空（状态码甚至不是 404，只是 `ERR`），极易误判为权限问题。

```python
# 错：条件判断写在赋值之后，编码块成了死代码
url = API + path
if not url.startswith("http"):
    url = encode(url)

# 对：先拼接，再无条件编码
url = enc_url(API + path)
```

编码时**只编码 path 部分**，保留 `scheme://` 与 `/`：

```python
quote(parts[1], safe="/~")
```

`safe="/~"` 不能省——否则整个 path 会被压成一段。

## 同步内容清单

| 类别 | 文件 |
|---|---|
| 文档 | `README.md` · `README.en.md` · `README-V1.0.md` · `LICENSE` |
| 依赖 | `requirements.txt` · `.gitignore` · `CONTRIBUTING.md` · `DEPENDENCIES.md` |
| 入口 | `demo.py` · `demo_evolution.py` · `run_filming.bat` · `rec_screen.bat` |
| 源码 | `src/{core,model,specs,verify}/` |
| 规范 | `docs/standards/SINOPORT-GEO-COD-26-001-V6.4.md` |
| 论文 | `docs/papers/`（作品介绍 · 同类方案对比） |
| 记录 | `docs/issues/`（Issue / PR 正文） |
| 产物 | `docs/reports/*.json` + 两张实测终端截图 |

---

_SINOSHOP 工程团队 · 2026-10-20_
_本目录不含任何凭据；令牌一律从环境变量读取。_
