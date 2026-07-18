"""HTTPS client for a WeChat publishing proxy.

Configuration is supplied explicitly or through environment variables:

    MP_PROXY_URL=https://proxy.example.com
    MP_PROXY_USERNAME=publisher
    MP_PROXY_PASSWORD=...
    MP_PROXY_CA_CERT=/path/to/proxy-ca.crt

Example:

    from mp_proxy.client import RemoteMP

    with RemoteMP() as mp:
        print(mp.health())
        cover_id = mp.upload_thumb("cover.jpg")
        draft_id = mp.add_draft(
            title="Article title",
            html_content="<p>Body</p>",
            thumb_media_id=cover_id,
        )
    draft_id = mp.add_draft(
        title="今日文章",
        html_content="<p>正文</p>",
        thumb_media_id="从 upload_thumb() 拿",
    )

TLS 自签证书 trust 方式：
    macOS:   sudo security add-trusted-cert -d -r trustRoot \
             -k /Library/Keychains/System.keychain mp-proxy.crt
    Linux:   sudo cp mp-proxy.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates
    Windows: 双击 .crt → Install Certificate → Local Machine → Trusted Root
    Python:  把 ca_cert 路径传给本客户端（已支持），**不要**全局 verify=False
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple, Union

import requests
from requests.auth import HTTPBasicAuth


DEFAULT_BASE_URL = os.environ.get("MP_PROXY_URL", "")


class MPErr(Exception):
    """mp_proxy 调用失败（含远端错误信息）。"""


class RemoteMP:
    """通过 HTTPS 反代操作公众号草稿/素材。

    支持上下文管理器（推荐）：复用同一个 requests.Session，
    多次调用复用同一个 TLS 连接，省 ~120ms 握手 / 调用。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth: Optional[Tuple[str, str]] = None,
        ca_cert: Optional[Union[str, Path]] = None,
        timeout: int = 120,
        verify: bool = True,
    ):
        resolved_base_url = base_url or os.environ.get("MP_PROXY_URL") or DEFAULT_BASE_URL
        if not resolved_base_url:
            raise ValueError("Missing proxy URL: pass base_url or set MP_PROXY_URL")
        if auth is None:
            username = os.environ.get("MP_PROXY_USERNAME")
            password = os.environ.get("MP_PROXY_PASSWORD")
            if username and password:
                auth = (username, password)
        if ca_cert is None:
            ca_cert = os.environ.get("MP_PROXY_CA_CERT")
        self.base_url = resolved_base_url.rstrip("/")
        self.auth_tuple = auth
        self.auth = HTTPBasicAuth(*auth) if auth else None
        self.ca_cert = str(ca_cert) if ca_cert else None
        self.timeout = timeout
        self.verify = verify  # 默认 True（要求配 ca_cert）
        self._sess: Optional[requests.Session] = None

    def __enter__(self):
        self._sess = requests.Session()
        self._sess.verify = self.ca_cert if self.ca_cert else self.verify
        if self.auth:
            self._sess.auth = self.auth
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._sess is not None:
            self._sess.close()
            self._sess = None
        return False

    # ---------- 低层 ----------

    def _post_json(self, path: str, payload: dict):
        url = f"{self.base_url}{path}"
        sess = self._sess or self._ensure_temp_session()
        try:
            r = sess.post(url, json=payload, timeout=self.timeout)
        except requests.exceptions.SSLError as e:
            raise MPErr(
                f"TLS 错误：{e}\n"
                f"  自签证书需要 ca_cert= 指向 mp-proxy.crt。\n"
                f"  绝对不要 verify=False（密码会裸传）。"
            )
        except requests.exceptions.ConnectionError as e:
            raise MPErr(f"连接失败：{e}")
        # 当前代理偶尔会把完整、有效的微信结果装在 HTTP 502 响应中返回。
        # 只接受与端点严格匹配的成功结构，其他 502 仍按错误处理。
        if r.status_code == 502:
            try:
                data = r.json()
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(data, dict):
                    if path == "/draft-get" and isinstance(data.get("news_item"), list):
                        return data
                    if path == "/draft-add" and isinstance(data.get("draft_media_id"), str):
                        return data
                    if path == "/draft-delete" and isinstance(data.get("deleted"), str):
                        return data
        return self._parse(r)

    def _post_file(self, path: str, file_path: Union[str, Path]):
        url = f"{self.base_url}{path}"
        sess = self._sess or self._ensure_temp_session()
        with open(file_path, "rb") as f:
            files = {"file": (Path(file_path).name, f)}
            r = sess.post(url, files=files, timeout=self.timeout)
        # 代理偶尔以 502 回传已被微信接受的上传结果；严格按端点
        # 所需字段识别，避免将成功上传误判为失败并造成重复素材。
        if r.status_code == 502:
            try:
                data = r.json()
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(data, dict):
                    if path == "/upload-thumb" and isinstance(data.get("media_id"), str):
                        return data
                    if path == "/upload-inline" and isinstance(data.get("url"), str):
                        return data
        return self._parse(r)

    def _ensure_temp_session(self):
        # 没在 with 块里时每次新建一个临时 Session（保证不全局泄漏连接）
        s = requests.Session()
        s.verify = self.ca_cert if self.ca_cert else self.verify
        if self.auth:
            s.auth = self.auth
        return s

    @staticmethod
    def _parse(r) -> dict:
        # 401/413/429 等也算远端正常响应，body 仍是 JSON
        try:
            data = r.json()
        except json.JSONDecodeError:
            raise MPErr(f"远端返回非 JSON（HTTP {r.status_code}）：{r.text[:200]}")
        if r.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            raise MPErr(f"HTTP {r.status_code} · {err or data}")
        if isinstance(data, dict) and data.get("ok") is False:
            raise MPErr(f"{data.get('error', 'unknown error')} (raw={data})")
        return data

    # ---------- 健康 ----------

    def health(self) -> dict:
        url = f"{self.base_url}/health"
        sess = self._sess or self._ensure_temp_session()
        r = sess.get(url, timeout=10)
        return r.json()

    # ---------- 草稿 ----------

    def add_draft(
        self,
        title: str,
        html_content: str,
        thumb_media_id: str,
        *,
        author: str = "",
        digest: str = "",
        content_source_url: str = "",
    ) -> str:
        article = {
            "title": title,
            "content": html_content,
            "thumb_media_id": thumb_media_id,
        }
        if author:
            article["author"] = author
        if digest:
            article["digest"] = digest
        if content_source_url:
            article["content_source_url"] = content_source_url
        result = self._post_json("/draft-add", {"articles": [article]})
        return result["draft_media_id"]

    def get_draft(self, draft_media_id: str) -> dict:
        return self._post_json("/draft-get", {"media_id": draft_media_id})

    def update_draft(
        self,
        draft_media_id: str,
        title: str,
        html_content: str,
        thumb_media_id: str,
        index: int = 0,
        author: str = "",
        digest: str = "",
    ) -> None:
        article = {"title": title, "content": html_content, "thumb_media_id": thumb_media_id}
        if author:
            article["author"] = author
        if digest:
            article["digest"] = digest
        self._post_json("/draft-update", {
            "media_id": draft_media_id,
            "index": index,
            "articles": [article],
        })

    def delete_draft(self, draft_media_id: str) -> None:
        self._post_json("/draft-delete", {"media_id": draft_media_id})

    # ---------- 上传 ----------

    def upload_thumb(self, file_path: Union[str, Path]) -> str:
        """上传封面图（永久素材），返回 media_id。"""
        result = self._post_file("/upload-thumb", file_path)
        return result["media_id"]

    def upload_inline_image(self, file_path: Union[str, Path]) -> str:
        """上传正文图片，返回 URL（mmbiz.qpic.cn/...）。"""
        result = self._post_file("/upload-inline", file_path)
        return result["url"]

    # ---------- 一站式 ----------

    def publish_article(
        self,
        *,
        title: str,
        html: str,
        cover_path: Union[str, Path],
        inline_image_paths: Optional[list] = None,
        author: str = "",
        digest: str = "",
    ) -> str:
        """一站式：上传封面 → 上传正文图替换占位 → 新增草稿。

        html 中用 {{INLINE_IMAGE:basename}} 占位，自动替换为 mmbiz URL。
        """
        inline_image_paths = inline_image_paths or []
        cover_id = self.upload_thumb(cover_path)
        url_map = {}
        for p in inline_image_paths:
            url_map[Path(p).name] = self.upload_inline_image(p)
        for fname, url in url_map.items():
            html = html.replace(f"{{{{INLINE_IMAGE:{fname}}}}}", url)
        return self.add_draft(
            title=title,
            html_content=html,
            thumb_media_id=cover_id,
            author=author,
            digest=digest,
        )


__all__ = ["RemoteMP", "MPErr", "DEFAULT_BASE_URL"]
