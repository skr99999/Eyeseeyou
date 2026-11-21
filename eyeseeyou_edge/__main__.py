"""Replay synthetic visual observations through the local fatigue rules."""

import argparse
import json
from pathlib import Path
import sys

from .replay import replay
from .report import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 JSONL file")
    parser.add_argument("--report", type=Path, metavar="FILE.html", help="write a standalone HTML replay report")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        with args.input.open("rb") as source:
            if args.report is not None:
                if args.report.exists() and args.report.samefile(args.input):
                    parser.error("report and input must be different files")
                write_report(args.report, args.input.name, replay(source))
            else:
                for decision in replay(source):
                    print(json.dumps(decision, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{args.input}: {exc}\n")


if __name__ == "__main__":
    main()
