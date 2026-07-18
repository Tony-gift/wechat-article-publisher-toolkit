# 微信公众号文章发布工具包

一套可复用的 Codex Skill 与轻量 HTTPS 客户端，用于把 Markdown 或 DOCX 稿件整理、校验并上传至微信公众号草稿箱。

## 项目内容

- `skill/`：完整的 `wechat-article-publisher` Skill，包含稿件导入、图片指令、清单校验、参考资料与示例。
- `mp_proxy/`：可复用会话的 HTTPS 客户端，用于连接独立部署的微信公众号发布代理。
- `tools/publish_draft.py`：通用草稿创建命令，支持语义化图片占位符替换与 SHA-256 上传缓存。
- `examples/`：最小可运行的文章、文章规划及图片清单示例。

本仓库不会收录微信公众号凭据、真实代理地址、私有 CA 证书、上传缓存、草稿 ID、未公开稿件或个人照片。

## 安装

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

参考 `.env.example` 配置环境变量。真实密码与 CA 证书应始终保存在仓库之外。

## 连接代理服务器

本仓库提供的是代理客户端，不包含代理服务端。使用前需要先取得一个兼容的 HTTPS 代理服务地址、Basic Auth 用户名和密码；如果服务使用自签名证书，还需要取得对应的 CA 证书文件。

代理服务端至少需要提供以下接口：

- `GET /health`：连通性检查；
- `POST /upload-thumb`：上传封面图；
- `POST /upload-inline`：上传正文图片；
- `POST /draft-add`、`/draft-get`、`/draft-update`、`/draft-delete`：管理公众号草稿。

在 PowerShell 中可这样配置当前终端：

```powershell
$env:MP_PROXY_URL = "https://proxy.example.com"
$env:MP_PROXY_USERNAME = "publisher"
$env:MP_PROXY_PASSWORD = "请替换为真实密码"
$env:MP_PROXY_CA_CERT = "C:\证书\mp-proxy-ca.crt"
```

Linux 或 macOS：

```bash
export MP_PROXY_URL="https://proxy.example.com"
export MP_PROXY_USERNAME="publisher"
export MP_PROXY_PASSWORD="请替换为真实密码"
export MP_PROXY_CA_CERT="/绝对路径/mp-proxy-ca.crt"
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
