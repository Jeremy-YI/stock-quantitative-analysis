"""报告输出（可插拔 notifier）。

抽象 ``Notifier`` 接口，实现两个：

    - ``FileNotifier``：把 Markdown 写到指定目录（默认）。
    - ``WebhookNotifier``：POST 到 webhook URL（默认飞书自定义机器人文本格式）。

飞书 webhook URL 从环境变量读，绝不硬编码；``.env.example`` 里只放占位符。
WebhookNotifier 通过注入 ``poster`` 可替换 HTTP 实现，单测用 mock 断言 payload。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol
from urllib import request

from scheduler.cron import TZ


class Notifier(Protocol):
    """报告输出接口。"""

    def send(self, job_name: str, title: str, content: str) -> None:
        """把一份报告发出去（文件 / webhook）。"""
        ...


class FileNotifier:
    """把 Markdown 写到 ``directory/{job_name}-{时间戳}.md``。"""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._dir

    def send(self, job_name: str, title: str, content: str) -> None:
        ts = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
        filename = f"{job_name}-{ts}.md"
        safe_title = title or job_name
        body = f"# {safe_title}\n\n{content}\n"
        (self._dir / filename).write_text(body, encoding="utf-8")


# poster 签名：接收 url + payload(dict)，返回 None（失败抛异常）
Poster = Callable[[str, dict], None]


def _default_poster(url: str, payload: dict) -> None:
    """默认 HTTP 实现（urllib，飞书自定义机器人文本格式的 JSON body）。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    request.urlopen(req, timeout=30).read()


class WebhookNotifier:
    """POST 到 webhook URL（默认飞书 text 消息格式）。

    可通过 ``poster`` 注入自定义 HTTP 实现（测试用 mock）。
    内容超长时按 ``max_chars`` 截断（飞书文本消息有长度上限）。
    """

    def __init__(
        self,
        url: str,
        poster: Poster | None = None,
        max_chars: int = 4000,
    ) -> None:
        self._url = url
        self._poster = poster or _default_poster
        self._max_chars = max_chars

    def send(self, job_name: str, title: str, content: str) -> None:
        text = f"{title}\n\n{content}" if title else content
        if len(text) > self._max_chars:
            text = text[: self._max_chars] + "\n…（已截断）"
        payload = {"msg_type": "text", "content": {"text": text}}
        self._poster(self._url, payload)
