"""README examples must reference real agents and the real committee schema.

Regression guard for release-blocking doc drift: `value-sage` is not a real
bundled agent card, and the committee example must match the top-level
`advisors:` schema used by examples/tradingagents_committee.yaml (not a
nested `committee: advisors:` block that PromptAgent does not understand).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


class TestReadmeAgentReferences:
    def test_readme_en_does_not_reference_nonexistent_value_sage_agent(self):
        assert "value-sage" not in _read("README.md")

    def test_readme_zh_does_not_reference_nonexistent_value_sage_agent(self):
        assert "value-sage" not in _read("README_zh.md")


class TestReadmeCommitteeExampleMatchesSchema:
    def test_readme_en_committee_example_uses_top_level_advisors_key(self):
        content = _read("README.md")
        assert "committee:\n  advisors:" not in content
        assert "advisors:" in content

    def test_readme_zh_committee_example_uses_top_level_advisors_key(self):
        content = _read("README_zh.md")
        assert "committee:\n  advisors:" not in content
