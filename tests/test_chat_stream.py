"""
Tests for the chat streaming generator.

We care about one behavior: when the Anthropic stream yields a
`tool_use` block followed by `input_json_delta` fragments, our generator
must emit a single `9:{toolName, args}\\n` frame containing the joined
JSON at the matching `content_block_stop`.

We replace `anthropic.Anthropic` with a fake that produces a predictable
event sequence, then read the generator output.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _evt(**kwargs):
    """Helper — Anthropic stream events are attribute-style objects."""
    return SimpleNamespace(**kwargs)


class _FakeStream:
    """Context manager that yields a scripted list of stream events."""

    def __init__(self, events, final_usage=(10, 5)):
        self._events = events
        self._final_usage = final_usage

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=self._final_usage[0],
                output_tokens=self._final_usage[1],
            )
        )


class _FakeMessages:
    def __init__(self, events):
        self._events = events

    def stream(self, **kwargs):  # noqa: ARG002 - matches the real signature
        return _FakeStream(self._events)


class _FakeAnthropic:
    def __init__(self, events):
        self.messages = _FakeMessages(events)


def _make_client(events, monkeypatch):
    """Return a TestClient whose /chat uses the scripted event stream."""
    import importlib

    import anthropic
    import app.routes.chat as chat_mod

    importlib.reload(chat_mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: _FakeAnthropic(events))

    # Bypass the _load_paper_blocks call so we don't need any PDFs on disk.
    monkeypatch.setattr(chat_mod, "_load_paper_blocks", lambda: [])
    # And a short system prompt so nothing blows up if knowledge/papers is empty.
    monkeypatch.setattr(chat_mod, "_build_system_prompt", lambda: "SYSTEM")

    app = FastAPI()
    app.include_router(chat_mod.router)
    return TestClient(app)


def _parse_frames(body: str):
    frames = []
    for line in body.split("\n"):
        if not line:
            continue
        prefix = line[0]
        payload = line[2:]
        frames.append((prefix, payload))
    return frames


def test_text_only_stream_produces_0_and_d_frames(monkeypatch):
    events = [
        _evt(type="content_block_start", content_block=SimpleNamespace(type="text")),
        _evt(type="content_block_delta", delta=SimpleNamespace(text="hello ")),
        _evt(type="content_block_delta", delta=SimpleNamespace(text="world")),
        _evt(type="content_block_stop"),
    ]
    c = _make_client(events, monkeypatch)
    r = c.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    frames = _parse_frames(r.text)
    kinds = [k for k, _ in frames]
    assert "0" in kinds
    assert kinds[-1] == "d"
    text = "".join(json.loads(p) for k, p in frames if k == "0")
    assert text == "hello world"


def test_tool_use_stream_emits_9_frame_with_args(monkeypatch):
    tool_block = SimpleNamespace(type="tool_use", name="trarpes_open")
    events = [
        _evt(type="content_block_start", content_block=tool_block),
        # Streaming JSON fragments (exactly what Anthropic sends)
        _evt(type="content_block_delta", delta=SimpleNamespace(partial_json='{"scan_a": ')),
        _evt(type="content_block_delta", delta=SimpleNamespace(partial_json="30, ")),
        _evt(type="content_block_delta", delta=SimpleNamespace(partial_json='"scan_b": 31}')),
        _evt(type="content_block_stop"),
    ]
    c = _make_client(events, monkeypatch)
    r = c.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "compare scan 30 and 31"}]},
    )
    assert r.status_code == 200
    frames = _parse_frames(r.text)
    # Exactly one 9: frame
    nine_frames = [p for k, p in frames if k == "9"]
    assert len(nine_frames) == 1
    payload = json.loads(nine_frames[0])
    assert payload["toolName"] == "trarpes_open"
    assert payload["args"] == {"scan_a": 30, "scan_b": 31}


def test_tool_use_with_no_args_emits_empty_args(monkeypatch):
    """Anthropic may yield a tool_use block with zero partial_json deltas."""
    tool_block = SimpleNamespace(type="tool_use", name="trarpes_open")
    events = [
        _evt(type="content_block_start", content_block=tool_block),
        _evt(type="content_block_stop"),
    ]
    c = _make_client(events, monkeypatch)
    r = c.post(
        "/chat", json={"messages": [{"role": "user", "content": "open it"}]}
    )
    assert r.status_code == 200
    frames = _parse_frames(r.text)
    nine_frames = [p for k, p in frames if k == "9"]
    assert len(nine_frames) == 1
    payload = json.loads(nine_frames[0])
    assert payload["toolName"] == "trarpes_open"
    assert payload["args"] == {}


def test_thinking_followed_by_text(monkeypatch):
    events = [
        _evt(type="content_block_start", content_block=SimpleNamespace(type="thinking")),
        _evt(type="content_block_delta", delta=SimpleNamespace(thinking="thinking...")),
        _evt(type="content_block_stop"),
        _evt(type="content_block_start", content_block=SimpleNamespace(type="text")),
        _evt(type="content_block_delta", delta=SimpleNamespace(text="answer")),
        _evt(type="content_block_stop"),
    ]
    c = _make_client(events, monkeypatch)
    r = c.post("/chat", json={"messages": [{"role": "user", "content": "q"}]})
    assert r.status_code == 200
    frames = _parse_frames(r.text)
    g_frames = [p for k, p in frames if k == "g"]
    t_frames = [p for k, p in frames if k == "0"]
    assert json.loads(g_frames[0])["text"] == "thinking..."
    assert json.loads(t_frames[0]) == "answer"


def test_mixed_text_and_tool_use(monkeypatch):
    """Common pattern: short lead-in text, then a tool-use block."""
    events = [
        _evt(type="content_block_start", content_block=SimpleNamespace(type="text")),
        _evt(type="content_block_delta", delta=SimpleNamespace(text="opening widget")),
        _evt(type="content_block_stop"),
        _evt(
            type="content_block_start",
            content_block=SimpleNamespace(type="tool_use", name="trarpes_open"),
        ),
        _evt(
            type="content_block_delta",
            delta=SimpleNamespace(partial_json='{"scan_a": 30}'),
        ),
        _evt(type="content_block_stop"),
    ]
    c = _make_client(events, monkeypatch)
    r = c.post("/chat", json={"messages": [{"role": "user", "content": "go"}]})
    assert r.status_code == 200
    frames = _parse_frames(r.text)
    zero = [p for k, p in frames if k == "0"]
    nine = [p for k, p in frames if k == "9"]
    assert zero and json.loads(zero[0]) == "opening widget"
    assert nine and json.loads(nine[0])["args"] == {"scan_a": 30}
