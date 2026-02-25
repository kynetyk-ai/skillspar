"""Tests for eval file discovery."""

import pytest

from skill_evaluator.discovery import DiscoveryError, resolve_eval_paths


class TestResolveEvalPaths:
    def test_single_file(self, tmp_path):
        f = tmp_path / "suite.eval.yaml"
        f.write_text("placeholder")

        result = resolve_eval_paths((str(f),))

        assert len(result) == 1
        assert result[0] == f.resolve()

    def test_directory_recursion(self, tmp_path):
        sub = tmp_path / "suites" / "nested"
        sub.mkdir(parents=True)
        f1 = tmp_path / "suites" / "a.eval.yaml"
        f2 = sub / "b.eval.yaml"
        f1.write_text("placeholder")
        f2.write_text("placeholder")
        # Non-eval file should be ignored
        (tmp_path / "suites" / "readme.md").write_text("ignore me")

        result = resolve_eval_paths((str(tmp_path / "suites"),))

        assert len(result) == 2
        resolved = {p.name for p in result}
        assert resolved == {"a.eval.yaml", "b.eval.yaml"}

    def test_glob_expansion(self, tmp_path):
        f1 = tmp_path / "a.eval.yaml"
        f2 = tmp_path / "b.eval.yaml"
        f3 = tmp_path / "c.txt"
        f1.write_text("placeholder")
        f2.write_text("placeholder")
        f3.write_text("placeholder")

        result = resolve_eval_paths((str(tmp_path / "*.eval.yaml"),))

        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"a.eval.yaml", "b.eval.yaml"}

    def test_nonexistent_path_raises(self):
        with pytest.raises(DiscoveryError, match="No .eval.yaml files found"):
            resolve_eval_paths(("/nonexistent/path.eval.yaml",))

    def test_deduplication(self, tmp_path):
        f = tmp_path / "suite.eval.yaml"
        f.write_text("placeholder")

        # Pass the same file twice
        result = resolve_eval_paths((str(f), str(f)))

        assert len(result) == 1

    def test_empty_directory_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()

        with pytest.raises(DiscoveryError, match="No .eval.yaml files found"):
            resolve_eval_paths((str(empty),))

    def test_sorted_output(self, tmp_path):
        for name in ["c.eval.yaml", "a.eval.yaml", "b.eval.yaml"]:
            (tmp_path / name).write_text("placeholder")

        result = resolve_eval_paths((str(tmp_path),))

        names = [p.name for p in result]
        assert names == sorted(names)

    def test_mixed_files_and_directories(self, tmp_path):
        f1 = tmp_path / "standalone.eval.yaml"
        f1.write_text("placeholder")
        sub = tmp_path / "subdir"
        sub.mkdir()
        f2 = sub / "nested.eval.yaml"
        f2.write_text("placeholder")

        result = resolve_eval_paths((str(f1), str(sub)))

        assert len(result) == 2
