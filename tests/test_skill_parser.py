"""Tests for skill/parser.py — SKILL.md parsing."""

import pytest

from skill_evaluator.skill.parser import ParsedSkill, SkillParseError, parse_skill


class TestParseSkill:
    def test_basic_skill(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: test\ndescription: A test skill\n---\n# Body\nContent")

        skill = parse_skill(skill_file)
        assert isinstance(skill, ParsedSkill)
        assert skill.name == "test"
        assert skill.description == "A test skill"
        assert "# Body" in skill.body
        assert "Content" in skill.body
        assert skill.source_path == skill_file

    def test_metadata_dict(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: foo\ncustom: bar\n---\nBody")

        skill = parse_skill(skill_file)
        assert skill.metadata == {"name": "foo", "custom": "bar"}

    def test_missing_name_uses_stem(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\ndescription: no name\n---\nBody")

        skill = parse_skill(skill_file)
        assert skill.name == "SKILL"

    def test_file_not_found(self, tmp_path):
        with pytest.raises(SkillParseError, match="not found"):
            parse_skill(tmp_path / "nonexistent.md")

    def test_no_frontmatter_delimiters(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("Just plain content")
        with pytest.raises(SkillParseError, match="frontmatter delimiters"):
            parse_skill(skill_file)

    def test_incomplete_frontmatter(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: test\nno closing delimiter")
        with pytest.raises(SkillParseError, match="incomplete"):
            parse_skill(skill_file)

    def test_invalid_yaml_frontmatter(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\n{{bad yaml\n---\nBody")
        with pytest.raises(SkillParseError, match="Invalid YAML"):
            parse_skill(skill_file)

    def test_non_dict_frontmatter(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\n- list item\n---\nBody")
        with pytest.raises(SkillParseError, match="mapping"):
            parse_skill(skill_file)
