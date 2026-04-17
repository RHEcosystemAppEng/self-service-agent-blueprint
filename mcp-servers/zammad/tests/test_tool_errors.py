"""Tool error formatting (ExceptionGroup visibility)."""

from zammad_mcp.server import _tool_error_text


def test_tool_error_text_plain() -> None:
    assert "ValueError" in _tool_error_text(ValueError("x"))
    assert "x" in _tool_error_text(ValueError("x"))


def test_tool_error_text_exception_group_single_child_unwraps() -> None:
    eg = ExceptionGroup("test", [RuntimeError("inner basher failure")])
    s = _tool_error_text(eg)
    assert s == "RuntimeError: inner basher failure"


def test_tool_error_text_exception_group_multiple_children() -> None:
    eg = ExceptionGroup(
        "multi",
        [RuntimeError("a"), ValueError("b")],
    )
    s = _tool_error_text(eg)
    assert "ExceptionGroup" in s
    assert "RuntimeError: a" in s
    assert "ValueError: b" in s
