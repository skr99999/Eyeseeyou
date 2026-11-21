"""Check the public CLI against the same three synthetic alert traces in any checkout."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


EXAMPLES = Path(__file__).resolve().parent
EXPECTED = {
    "fatigue": [(12500, "request_fatigue_alert"), (13250, "clear_fatigue_alert")],
    "camera_gap": [],
    "tracking_loss": [],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, default=EXAMPLES.parent,
                        help="checkout containing the eyeseeyou_edge package to run")
    root = parser.parse_args().engine_dir.resolve()
    if not (root / "eyeseeyou_edge" / "__main__.py").is_file():
        parser.error(f"no EyeSeeYou Edge CLI found in {root}")
    passed = 0
    for name, expected in EXPECTED.items():
        sample = EXAMPLES / f"{name}.jsonl"
        times = [json.loads(line)["t_ms"] for line in sample.read_bytes().splitlines()]
        result = subprocess.run([sys.executable, "-E", "-B", "-m", "eyeseeyou_edge", str(sample)],
                                cwd=root, capture_output=True)
        if result.returncode:
            print(f"ERROR {name}: {result.stderr.decode('utf-8', errors='replace')}", file=sys.stderr)
            return 2
        decisions = [json.loads(line) for line in result.stdout.splitlines()]
        if [row["t_ms"] for row in decisions] != times:
            print(f"FAIL {name}: output timestamps differ from input")
            continue
        actions = [(row["t_ms"], row["action"]) for row in decisions if row["action"] is not None]
        if actions == expected:
            print(f"PASS {name} ({len(times)} frames): {actions}")
            passed += 1
        else:
            print(f"FAIL {name}: expected {expected}, got {actions}")
    print(f"{passed}/{len(EXPECTED)} scenarios passed")
    return int(passed != len(EXPECTED))


if __name__ == "__main__":
    sys.exit(main())
