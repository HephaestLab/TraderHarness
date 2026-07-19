"""Refresh a staged Hugging Face dataset card and its verified manifest entry."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from traderharness.data.release import build_dataset_card  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("staging", type=Path)
    args = parser.parse_args()

    manifest_path = args.staging / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    readme = args.staging / "README.md"
    old_bytes = readme.stat().st_size if readme.is_file() else 0
    readme.write_text(build_dataset_card(), encoding="utf-8")
    payload = readme.read_bytes()
    entry = next(item for item in manifest["files"] if item["path"] == "README.md")
    entry["bytes"] = len(payload)
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest["total_bytes"] = int(manifest["total_bytes"]) - old_bytes + len(payload)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {readme} and manifest ({len(payload):,} bytes)")


if __name__ == "__main__":
    main()
