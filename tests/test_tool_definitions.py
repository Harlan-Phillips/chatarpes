"""
Sanity tests for the Anthropic tool schema.

The model-facing schema has a specific shape (name/description/input_schema);
a typo here silently breaks tool-calling. These tests catch the obvious
regressions.
"""

from __future__ import annotations

from app.tools.tool_definitions import ANTHROPIC_TOOLS


def test_anthropic_tools_is_a_list():
    assert isinstance(ANTHROPIC_TOOLS, list)
    assert len(ANTHROPIC_TOOLS) >= 1


def test_trarpes_open_tool_present():
    by_name = {t["name"]: t for t in ANTHROPIC_TOOLS}
    assert "trarpes_open" in by_name


def test_tool_shape_conforms_to_anthropic_api():
    for tool in ANTHROPIC_TOOLS:
        assert "name" in tool
        assert "description" in tool and tool["description"]
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_trarpes_open_accepts_optional_scan_numbers():
    t = next(t for t in ANTHROPIC_TOOLS if t["name"] == "trarpes_open")
    props = t["input_schema"]["properties"]
    assert "scan_a" in props and "scan_b" in props
    # Both nullable so the model can call with no args
    for key in ("scan_a", "scan_b"):
        t_decl = props[key]["type"]
        assert "integer" in t_decl
        assert "null" in t_decl
    # Neither required — we want the model to be able to call it with no args
    assert t["input_schema"].get("required", []) == []
