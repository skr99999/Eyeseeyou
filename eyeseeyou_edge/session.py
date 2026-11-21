"""Preview a local study plan or explicitly start an in-memory focus session."""

import argparse
import json
from pathlib import Path
import sys

from .database import Database
from .focus import FocusSessionController
from .plan import confirm_plan, preview_plan


def start_session(plan: dict, *, confirmed: bool) -> dict:
    request = confirm_plan(plan, confirmed=confirmed)
    database = Database(Path(":memory:"))
    try:
        controller = FocusSessionController({}, database)
        result = controller.command(request["command"], request["payload"])
        state = result["state"]
        return {
            "command": request["command"],
            "event": result["event"]["type"],
            "state": state["state"],
            "current_task": state["current_task"],
            "duration_seconds": state["duration_seconds"],
            "remaining_seconds": state["remaining_seconds"],
        }
    finally:
        database.conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", help="study goal with an optional duration")
    parser.add_argument("--confirm", action="store_true", help="start a focus session for this demonstration")
    args = parser.parse_args()
    try:
        plan = preview_plan(args.goal)
        result = {"plan": plan}
        if args.confirm:
            result["session"] = start_session(plan, confirmed=True)
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
