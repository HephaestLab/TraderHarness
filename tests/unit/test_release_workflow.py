"""Release automation must prove that public installation artifacts exist."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_release_builds_and_checks_one_shared_distribution() -> None:
    assert "package:" in WORKFLOW
    assert "python -m twine check dist/*" in WORKFLOW
    assert "actions/upload-artifact@v4" in WORKFLOW
    assert "name: release-dist" in WORKFLOW


def test_pypi_publish_uses_the_checked_distribution() -> None:
    assert "needs: package" in WORKFLOW
    assert "actions/download-artifact@v4" in WORKFLOW
    assert "pypa/gh-action-pypi-publish@release/v1" in WORKFLOW


def test_release_verifies_the_version_from_public_pypi() -> None:
    assert "verify-pypi:" in WORKFLOW
    assert "https://pypi.org/pypi/traderharness/${VERSION}/json" in WORKFLOW
    assert "importlib.metadata.version('traderharness')" in WORKFLOW


def test_github_release_attaches_wheel_and_sdist() -> None:
    assert "needs: [package, verify-pypi, container]" in WORKFLOW
    assert "files: dist/*" in WORKFLOW
    assert "fail_on_unmatched_files: true" in WORKFLOW
