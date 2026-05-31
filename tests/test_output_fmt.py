"""aicode.cli.output_fmt — Markdown-ish → terminal ANSI."""
from __future__ import annotations

import re

from aicode.cli.output_fmt import format_assistant_markdown
from aicode.core.assistant_markdown_stream import AssistantMarkdownStreamWriter

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _pipe_positions(line: str) -> list[int]:
    return [i for i, ch in enumerate(line) if ch == "|"]


def test_bold_double_star():
    s = format_assistant_markdown("Hello **world** end")
    assert "\033[1m" in s
    assert "world" in s
    assert "\033[0m" in s
    assert "**" not in s


def test_bold_multiple_segments():
    s = format_assistant_markdown("**a** and **b**")
    assert s.count("\033[1m") == 2


def test_code_fence_renders_as_panel_without_inline_markdown():
    raw = "Use `**` like this:\n```\n**not bold**\n```\nDone **yes**."
    s = format_assistant_markdown(raw)
    plain = _strip_ansi(s)
    assert "**not bold**" in s
    assert "\033[1myes\033[0m" in s
    assert "```" not in plain
    assert "╭─ code" in plain


def test_python_code_fence_shows_language_label():
    raw = "```python\ndef hello():\n    print('hi')\n```"
    s = _strip_ansi(format_assistant_markdown(raw))
    assert "╭─ python" in s
    assert "│ def hello():" in s
    assert "│     print('hi')" in s
    assert "```python" not in s


def test_empty():
    assert format_assistant_markdown("") == ""


def test_gfm_table_columns_padded():
    raw = (
        "| Tool | Desc |\n"
        "|------|------|\n"
        "| `read_file` | read files |\n"
        "| `w` | short |\n"
    )
    s = format_assistant_markdown(raw)
    lines = [ln for ln in s.splitlines() if ln.strip().startswith("|")]
    assert len(lines) == 4
    pipe_counts = [ln.count("|") for ln in lines]
    assert pipe_counts[0] == pipe_counts[1] == pipe_counts[2] == pipe_counts[3]
    assert "read_file" in s
    # 窄单元格右侧补空格，与「read files」列对齐
    assert "| \033[2;48;5;236m w \033[0m" in s


def test_stream_bold_split_across_chunks():
    out: list[str] = []
    w = AssistantMarkdownStreamWriter(out.append)
    w.write("Hi **wo")
    w.write("rd** tail")
    w.flush()
    joined = "".join(out)
    assert "\033[1mword\033[0m" in joined
    assert "tail" in joined


def test_stream_plain_text_without_newline_emits_before_flush():
    out: list[str] = []
    w = AssistantMarkdownStreamWriter(out.append)

    w.write("Hello ")
    w.write("world")

    assert "".join(out) == "Hello world"


def test_stream_fence_keeps_inner_stars():
    out: list[str] = []
    w = AssistantMarkdownStreamWriter(out.append)
    w.write("```\n**no**\n``")
    w.write("`\n**yes**")
    w.flush()
    joined = "".join(out)
    plain = _strip_ansi(joined)
    assert "**no**" in joined
    assert "\033[1myes\033[0m" in joined
    assert "```" not in plain
    assert "╭─ code" in plain


def test_stream_python_fence_renders_after_close():
    out: list[str] = []
    w = AssistantMarkdownStreamWriter(out.append)
    w.write("```py")
    assert "".join(out) == ""
    w.write("thon\nprint('hi')\n")
    assert "".join(out) == ""
    w.write("```")
    joined = _strip_ansi("".join(out))
    assert "╭─ python" in joined
    assert "│ print('hi')" in joined
    assert "```" not in joined


def test_heading_atx_bold_body():
    s = format_assistant_markdown("### Section **one**\nplain")
    assert "\033[1m" in s
    assert "Section" in s
    assert "###" not in s


def test_unordered_list_bullet():
    s = format_assistant_markdown("- first\n- **bold** item")
    assert "•" in s
    assert "\033[1mbold\033[0m" in s


def test_ordered_list_dim_number():
    s = format_assistant_markdown("1. step one\n2. **two**")
    assert "\033[2m1.\033[0m" in s
    assert "\033[1mtwo\033[0m" in s


def test_unordered_list_star_marker():
    s = format_assistant_markdown("* alpha\n+ beta")
    assert s.count("•") == 2


def test_unordered_list_unicode_dash_markers():
    # en-dash / em-dash / minus sign / fullwidth hyphen-minus
    s = format_assistant_markdown("– a\n— b\n− c\n－ d")
    assert s.count("•") == 4


def test_ordered_list_parenthesis_marker():
    s = format_assistant_markdown("1) first\n2) second")
    assert "\033[2m1)\033[0m" in s
    assert "\033[2m2)\033[0m" in s


def test_inline_code_backticks():
    s = format_assistant_markdown("run `python app.py` now")
    assert "python app.py" in s
    assert "\033[2;48;5;236m" in s


def test_inline_link_and_strikethrough():
    s = _strip_ansi(format_assistant_markdown("Open [docs](https://example.test) and ~~skip~~"))
    assert "docs (https://example.test)" in s
    assert "skip" in s
    assert "~~" not in s


def test_horizontal_rule_rendered():
    s = format_assistant_markdown("---\ntext")
    assert "─" in s
    assert "text" in s


def test_gfm_table_cjk_display_width_alignment():
    raw = (
        "| 列 | Desc |\n"
        "|----|------|\n"
        "| 汉 | x |\n"
        "| aa | y |\n"
    )
    s = format_assistant_markdown(raw)
    lines = [ln for ln in s.splitlines() if ln.strip().startswith("|")]
    assert len(lines) == 4
    # 若错误按 len() 计算，"汉" 行会出现额外空格，这里应紧贴单个空格分隔
    assert "| 汉 | x" in lines[2]


def test_controls_table_pipe_positions_align():
    raw = (
        "Controls:\n"
        "| Key | Action |\n"
        "|-----|--------|\n"
        "| ↑↓←→ or WASD | Move tiles |\n"
        "| R | Restart |\n"
        "| Q | Quit |\n"
        "| C | Continue after winning |\n"
    )
    s = _strip_ansi(format_assistant_markdown(raw))
    lines = [ln for ln in s.splitlines() if ln.startswith("|")]
    positions = [_pipe_positions(ln) for ln in lines]
    assert len(lines) == 6
    assert all(pos == positions[0] for pos in positions)


def test_stream_gfm_table_waits_for_complete_block():
    out: list[str] = []
    w = AssistantMarkdownStreamWriter(out.append)
    for piece in [
        "Controls:\n| Key | Action |\n",
        "|-----|--------|\n",
        "| ↑↓←→ or WASD | Move tiles |\n",
        "| R | Restart |\n",
        "Done",
    ]:
        w.write(piece)
    w.flush()
    joined = _strip_ansi("".join(out))
    lines = [ln for ln in joined.splitlines() if ln.startswith("|")]
    positions = [_pipe_positions(ln) for ln in lines]
    assert len(lines) == 4
    assert all(pos == positions[0] for pos in positions)
    assert joined.index("Controls:") < joined.index("| Key")
    assert joined.index("| R") < joined.index("Done")


def test_stream_markdown_enabled_respects_aicode_color_override(monkeypatch):
    from aicode.core.loop import _stream_markdown_enabled

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("AICODE_COLOR", "1")

    assert _stream_markdown_enabled() is True


def test_stream_heading_split_chunks():
    out: list[str] = []
    w = AssistantMarkdownStreamWriter(out.append)
    w.write("### My ")
    assert "".join(out) == ""
    w.write("Title\nnext")
    w.flush()
    joined = "".join(out)
    assert "###" not in joined
    assert "\033[1mMy Title\033[0m" in joined
    assert "next" in joined
