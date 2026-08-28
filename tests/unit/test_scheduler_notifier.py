"""Notifier 单测：FileNotifier 写出内容正确，WebhookNotifier 用 mock 断言 payload。"""

from __future__ import annotations

from scheduler.notifier import FileNotifier, WebhookNotifier


def test_file_notifier_writes_markdown(tmp_path):
    n = FileNotifier(tmp_path)
    n.send("daily_report", "标题", "# 正文\n\n- 条目")
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    assert files[0].name.startswith("daily_report-")
    content = files[0].read_text(encoding="utf-8")
    assert content.startswith("# 标题")
    assert "# 正文" in content
    assert "- 条目" in content


def test_webhook_notifier_posts_feishu_text_payload():
    captured: dict = {}

    def fake_poster(url, payload):
        captured["url"] = url
        captured["payload"] = payload

    w = WebhookNotifier("https://example.com/hook", poster=fake_poster)
    w.send("daily_report", "标题", "正文内容")
    assert captured["url"] == "https://example.com/hook"
    assert captured["payload"]["msg_type"] == "text"
    assert "标题" in captured["payload"]["content"]["text"]
    assert "正文内容" in captured["payload"]["content"]["text"]


def test_webhook_notifier_truncates_long_content():
    captured: dict = {}

    def fake_poster(url, payload):
        captured["payload"] = payload

    w = WebhookNotifier("https://example.com/hook", poster=fake_poster, max_chars=20)
    w.send("j", "标题", "A" * 100)
    text = captured["payload"]["content"]["text"]
    # 截断到 max_chars 后追加后缀，总长应远小于原始内容
    assert "…（已截断）" in text
    assert len(text) < 100
