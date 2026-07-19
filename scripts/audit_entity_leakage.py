"""Audit Agent-visible trajectory/prompt artifacts for identity/date leakage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from traderharness.audit import audit_artifacts  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", type=Path, nargs="+")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--max-findings", type=int, default=100)
    args = parser.parse_args()

    report = audit_artifacts(args.artifacts, max_findings=args.max_findings)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_output:
        args.json_output.write_text(payload, encoding="utf-8")
    print(payload)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
