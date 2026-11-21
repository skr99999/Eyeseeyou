"""Replay an absence, a stable return, and an explicit confirmation to resume."""

from contextlib import closing
from pathlib import Path

from eyeseeyou_edge.database import Database
from eyeseeyou_edge.focus import FocusSessionController
from eyeseeyou_edge.models import FaceResult, VisionObservation
from eyeseeyou_edge.plan import confirm_plan, preview_plan


def main():
    request = confirm_plan(preview_plan("背单词 20 分钟"), confirmed=True)
    database = Database(Path(":memory:"))
    with closing(database.conn):
        controller = FocusSessionController({}, database)
        present = VisionObservation(face=FaceResult(found=True))
        absent = VisionObservation(face=FaceResult(found=False))

        def show(now, event):
            status = controller.status()
            print(f"{now:2}s  {event:25} {status['state']:7} remaining={status['remaining_seconds']:g}s")

        started = controller.command(request["command"], request["payload"], now=1)
        controller.update(present, now=1)
        show(1, started["event"]["type"])

        for now in range(2, 37):
            observation = absent if now <= 32 else present
            for event in controller.update(observation, now=now):
                show(now, event["type"])
        show(36, "waiting_for_confirmation")

        resumed = controller.command("resolve_recovery", {"action": "continue"}, now=36)
        show(36, resumed["event"]["type"])
        controller.update(present, now=37)
        show(37, "countdown")


if __name__ == "__main__":
    main()
