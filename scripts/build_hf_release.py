"""Build the verified public HuggingFace dataset staging directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from traderharness.data.release import build_release  # noqa: E402
from traderharness.paths import dataset_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=dataset_dir())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest = build_release(args.source, args.output, force=args.force)
    print(
        json.dumps(
            {
                "files": len(manifest["files"]),
                "total_bytes": manifest["total_bytes"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
