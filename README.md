# 微信公众号文章发布工具包

一套可复用的 Codex Skill 与轻量 HTTPS 客户端，用于把 Markdown 或 DOCX 稿件整理、校验并上传至微信公众号草稿箱。

## 项目内容

- `skill/`：完整的 `wechat-article-publisher` Skill，包含稿件导入、图片指令、清单校验、参考资料与示例。
- `mp_proxy/`：可复用会话的 HTTPS 客户端，用于连接独立部署的微信公众号发布代理。
- `tools/publish_draft.py`：通用草稿创建命令，支持语义化图片占位符替换与 SHA-256 上传缓存。
- `examples/`：最小可运行的文章、文章规划及图片清单示例。

本仓库不会收录微信公众号凭据、真实代理地址、用户实际使用的证书、上传缓存、草稿 ID、未公开稿件或个人照片。

## 安装

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

参考 `.env.example` 配置环境变量。真实密码不得写入仓库；自签名服务器的公开证书可放在本地项目的 `certs/` 目录，该目录中的证书文件默认不会被 Git 跟踪。

## 连接代理服务器

本仓库提供的是代理客户端，不包含代理服务端。使用前需要先取得一个兼容的 HTTPS 代理服务地址、Basic Auth 用户名和密码；如果服务使用自签名证书，还需要取得用于校验服务器身份的 `.crt` 证书。

代理服务端至少需要提供以下接口：

- `GET /health`：连通性检查；
- `POST /upload-thumb`：上传封面图；
- `POST /upload-inline`：上传正文图片；
- `POST /draft-add`、`/draft-get`、`/draft-update`、`/draft-delete`：管理公众号草稿。

推荐把取得的公开证书复制为：

```text
wechat-article-publisher-toolkit/
└── certs/
    └── mp-proxy.crt
```

然后在项目根目录打开 PowerShell，配置当前终端：

```powershell
$env:MP_PROXY_URL = "https://proxy.example.com"
$env:MP_PROXY_USERNAME = "publisher"
$env:MP_PROXY_PASSWORD = "请替换为真实密码"
$env:MP_PROXY_CA_CERT = ".\certs\mp-proxy.crt"
```

Linux 或 macOS：

```bash
export MP_PROXY_URL="https://proxy.example.com"
export MP_PROXY_USERNAME="publisher"
export MP_PROXY_PASSWORD="请替换为真实密码"
export MP_PROXY_CA_CERT="./certs/mp-proxy.crt"
```

配置后先测试连接：

```bash
python -c "from mp_proxy import RemoteMP; mp=RemoteMP(); print(mp.health())"
```

若返回内容中包含 `"ok": true`，即可继续创建草稿。完整的接入条件、接口约定、证书处理、测试方法与故障排查见：[代理服务器连接指南](docs/代理服务器连接指南.md)。

## 安装 Codex Skill

将 `skill/` 复制到 Codex 的 Skills 目录，并使用类似下面的目录名：

```text
wechat-article-publisher/
```

该 Skill 可导入 Markdown 或 DOCX、提取内嵌图片、生成文章规划与图片清单、校验微信公众号兼容的 HTML，并在获得明确确认后创建草稿。

## 发布前规则校验

微信公众号草稿标题按 UTF-8 字节数计算，最多 64 字节。规划文件中的 `title` 保留作品完整原题；当原题超限时，另设精简的 `draft_title` 作为草稿列表标题，正文标题仍展示完整原题。

中文散文、评论等普通正文段落优先使用 CSS `text-indent:2em` 实现首行缩进；若目标 API 的实际回读会清除该属性，则在最终 HTML 中使用两个 `&emsp;` 作为经过验证的兼容回退。不要在段首手打全角空格，也不要用空段落或连续 `<br>` 撑开间距；标题、诗歌、标签和经过设计的开篇导语可不缩进。

可在发布前运行严格校验：

```bash
python skill/scripts/validate_draft_layout.py \
  examples/article-plan.json \
  examples/article.html \
  --mode prose \
  --strict-warnings
```

校验会检查标题长度、精简标题、空段落、段首空格、全角空格、重复换行，以及正文的字号、行距、段距、对齐与首行缩进。仓库 CI 也会执行同一命令。

## 创建已校验的公众号草稿

先准备包含语义化图片占位符的 HTML 排版源文件：

```html
<img src="{{IMAGE:hero}}" alt="社团成员共读">
```

然后运行：

```bash
python tools/publish_draft.py \
  --title "文章标题" \
  --html examples/article.html \
  --cover /path/to/cover.jpg \
  --image hero=/path/to/hero.jpg
```

该命令会：

1. 校验排版源文件；
2. 按接口类型与 SHA-256 复用上传缓存；
3. 上传封面及正文图片；
4. 按语义槽位 ID 替换图片占位符；
5. 创建微信公众号草稿并回读核验；
6. 输出草稿媒体 ID 与校验报告。

该工具只写入草稿箱，不会群发或正式发布文章。

## 安全说明

详见 [SECURITY.md](SECURITY.md)。仓库仅包含客户端接口约定，不包含代理服务端。

## 交流联系

如需交流排版、Skill 使用或微信公众号草稿发布流程，可添加微信：`tonyywwq`。

## 许可说明

本项目暂未授予开源许可证。在转载、再分发或接受外部贡献前，请先补充合适的许可证。
