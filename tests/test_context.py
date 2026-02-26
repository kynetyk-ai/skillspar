"""Tests for engine/context.py — context file resolution, reading, and message building."""

import pytest

from skill_evaluator.config.schema import ContextFileConfig
from skill_evaluator.engine.context import (
    ContextFileError,
    build_context_messages,
    read_context_file,
    resolve_context_file,
)

# ---------------------------------------------------------------------------
# resolve_context_file
# ---------------------------------------------------------------------------


class TestResolveContextFile:
    def test_relative_path_resolved(self, tmp_path):
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir()
        ref_file.write_text("print('hello')")
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()

        result = resolve_context_file(eval_file, "./src/main.py")
        assert result == ref_file.resolve()

    def test_missing_file_raises(self, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()

        with pytest.raises(ContextFileError, match="not found"):
            resolve_context_file(eval_file, "./nonexistent.py")

    def test_directory_raises(self, tmp_path):
        dir_path = tmp_path / "some_dir"
        dir_path.mkdir()
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()

        with pytest.raises(ContextFileError, match="not a file"):
            resolve_context_file(eval_file, "./some_dir")


# ---------------------------------------------------------------------------
# read_context_file
# ---------------------------------------------------------------------------


class TestReadContextFile:
    def test_full_file(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("line1\nline2\nline3")
        result = read_context_file(f)
        assert "     1\tline1" in result
        assert "     2\tline2" in result
        assert "     3\tline3" in result

    def test_line_range(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("a\nb\nc\nd\ne")
        result = read_context_file(f, lines=[2, 4])
        assert "     2\tb" in result
        assert "     3\tc" in result
        assert "     4\td" in result
        assert "1\ta" not in result
        assert "5\te" not in result

    def test_range_exceeds_length(self, tmp_path):
        f = tmp_path / "short.py"
        f.write_text("a\nb")
        result = read_context_file(f, lines=[1, 100])
        assert "     1\ta" in result
        assert "     2\tb" in result

    def test_start_beyond_length(self, tmp_path):
        f = tmp_path / "short.py"
        f.write_text("a\nb")
        result = read_context_file(f, lines=[10, 20])
        assert "2 lines" in result
        assert "requested start 10" in result

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        result = read_context_file(f)
        assert result == ""

    def test_single_line(self, tmp_path):
        f = tmp_path / "one.py"
        f.write_text("only")
        result = read_context_file(f, lines=[1, 1])
        assert "     1\tonly" in result

    def test_binary_file_raises(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x80\xff")
        with pytest.raises(ContextFileError, match="binary file"):
            read_context_file(f)


# ---------------------------------------------------------------------------
# build_context_messages
# ---------------------------------------------------------------------------


class TestBuildContextMessages:
    def test_single_file(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("print('hello')")
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()

        ctx = [ContextFileConfig(file="./hello.py")]
        msgs = build_context_messages(eval_file, ctx)

        assert len(msgs) == 3
        assert msgs[0].role == "user"
        assert msgs[0].content == "[Reading context files]"
        assert msgs[1].role == "assistant"
        assert len(msgs[1].tool_calls) == 1
        assert msgs[1].tool_calls[0].name == "Read"
        assert msgs[1].tool_calls[0].id == "ctx_0001"
        assert msgs[2].role == "tool_result"
        assert msgs[2].tool_use_id == "ctx_0001"

    def test_multiple_files_batched(self, tmp_path):
        (tmp_path / "a.py").write_text("aaa")
        (tmp_path / "b.py").write_text("bbb")
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()

        ctx = [ContextFileConfig(file="./a.py"), ContextFileConfig(file="./b.py")]
        msgs = build_context_messages(eval_file, ctx)

        assert len(msgs) == 4  # user, assistant, tool_result, tool_result
        assert len(msgs[1].tool_calls) == 2
        assert msgs[1].tool_calls[0].id == "ctx_0001"
        assert msgs[1].tool_calls[1].id == "ctx_0002"
        assert msgs[2].tool_use_id == "ctx_0001"
        assert msgs[3].tool_use_id == "ctx_0002"

    def test_tool_ids_sequential(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text(f"file {i}")
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()

        ctx = [ContextFileConfig(file=f"./f{i}.py") for i in range(5)]
        msgs = build_context_messages(eval_file, ctx)

        ids = [tc.id for tc in msgs[1].tool_calls]
        assert ids == ["ctx_0001", "ctx_0002", "ctx_0003", "ctx_0004", "ctx_0005"]

    def test_line_range_in_read_input(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("\n".join(f"line {i}" for i in range(1, 101)))
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()

        ctx = [ContextFileConfig(file="./big.py", lines=[10, 20])]
        msgs = build_context_messages(eval_file, ctx)

        read_input = msgs[1].tool_calls[0].input
        assert read_input["offset"] == 10
        assert read_input["limit"] == 11

    def test_empty_list_returns_empty(self, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()
        assert build_context_messages(eval_file, []) == []

    def test_content_matches_read(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("print('hello')\nprint('world')")
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.touch()

        ctx = [ContextFileConfig(file="./hello.py")]
        msgs = build_context_messages(eval_file, ctx)

        expected = read_context_file(f)
        assert msgs[2].content == expected
