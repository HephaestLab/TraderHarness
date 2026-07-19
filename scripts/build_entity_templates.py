"""Build entity-templated announcement/news files for masked runs and HF release.

Real company names and observed announcement aliases become ``{{C600519}}``.
At runtime EntityMasker resolves these placeholders to the run-scoped neutral
label without exposing the real code/name association to the Agent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from traderharness.data.entity_templates import EntityTemplateMap, build_alias_map  # noqa: E402
from traderharness.data.stock_registry_loader import get_stock_registry  # noqa: E402
from traderharness.paths import dataset_dir  # noqa: E402


def _atomic_parquet(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(destination)


def build(source_dir: Path, output_dir: Path) -> dict[str, Path]:
    announcements_path = source_dir / "announcements.parquet"
    news_path = source_dir / "news_cls.parquet"
    if not announcements_path.exists() or not news_path.exists():
        missing = [str(path) for path in (announcements_path, news_path) if not path.exists()]
        raise FileNotFoundError("Missing source datasets: " + ", ".join(missing))

    announcements = pd.read_parquet(announcements_path)
    aliases = build_alias_map(get_stock_registry(), announcements)
    templates = EntityTemplateMap(aliases)

    templated_announcements = templates.template_frame(
        announcements,
        ["stock_name", "title"],
    )
    news = pd.read_parquet(news_path)
    templated_news = templates.template_frame(news, ["title", "content"])

    outputs = {
        "announcements": output_dir / "announcements_templated.parquet",
        "news": output_dir / "news_cls_templated.parquet",
    }
    _atomic_parquet(templated_announcements, outputs["announcements"])
    _atomic_parquet(templated_news, outputs["news"])
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=dataset_dir())
    parser.add_argument("--output-dir", type=Path, default=dataset_dir())
    args = parser.parse_args()

    outputs = build(args.source_dir, args.output_dir)
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
