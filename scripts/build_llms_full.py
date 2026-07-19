"""Build the single-file AI-readable documentation bundle."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    ROOT / "README.md",
    ROOT / "docs" / "quickstart.md",
    ROOT / "docs" / "contamination.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "comparison.md",
    ROOT / "docs" / "design" / "multi-role-agent.md",
    ROOT / "docs" / "training-data.md",
    ROOT / "docs" / "data.md",
    ROOT / "docs" / "api.md",
    ROOT / "docs" / "extensions.md",
    ROOT / "docs" / "roadmap.md",
    ROOT / "docs" / "faq.md",
]
OUTPUT = ROOT / "llms-full.txt"


def main() -> None:
    sections = [
        "# TraderHarness full documentation\n\n"
        "Canonical source: https://github.com/HephaestLab/TraderHarness\n\n"
        "This file is generated from the public README and documentation pages."
    ]
    for path in DOCUMENTS:
        relative = path.relative_to(ROOT).as_posix()
        sections.append(f"\n\n---\n\n<!-- source: {relative} -->\n\n{path.read_text(encoding='utf-8').strip()}")
    OUTPUT.write_text("".join(sections) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} from {len(DOCUMENTS)} documents")


if __name__ == "__main__":
    main()
