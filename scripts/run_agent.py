#!/usr/bin/env python3
"""Run the Mandarin Market Oracle research agent from the command line."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oracle.engine import OracleService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run compliance-safe research recommendations.")
    parser.add_argument("--signal", help="Optional live or user-submitted signal id.")
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Print the full product snapshot instead of only recommendations.",
    )
    args = parser.parse_args()

    service = OracleService()
    payload = (
        service.snapshot().model_dump(mode="json")
        if args.snapshot
        else [
            item.model_dump(mode="json")
            for item in service.recommendations(signal_id=args.signal)
        ]
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
