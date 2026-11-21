import json
from pathlib import Path
import subprocess
import sys
import unittest

from eyeseeyou_edge.plan import preview_plan
from eyeseeyou_edge.session import start_session


class SessionTest(unittest.TestCase):
    def test_return_waits_until_confirmation(self):
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-B", "-m", "examples.away_return"]
        output = subprocess.check_output(command, cwd=root, text=True)
        self.assertEqual([line.split() for line in output.splitlines()], [
            ["1s", "focus_started", "RUNNING", "remaining=1200s"],
            ["32s", "away", "AWAY", "remaining=1169s"],
            ["35s", "recovery_prompted", "AWAY", "remaining=1169s"],
            ["36s", "waiting_for_confirmation", "AWAY", "remaining=1169s"],
            ["36s", "recovery_continued", "RUNNING", "remaining=1169s"],
            ["37s", "countdown", "RUNNING", "remaining=1168s"],
        ])

    def test_preview_then_confirm(self):
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-B", "-m", "eyeseeyou_edge.session", "背单词 20 分钟"]
        preview = subprocess.check_output(command, cwd=root)
        started = subprocess.check_output(command + ["--confirm"], cwd=root)
        preview, started = json.loads(preview), json.loads(started)
        self.assertEqual(set(preview), {"plan"})
        self.assertEqual(preview["plan"], started["plan"])
        self.assertEqual(preview["plan"]["total_seconds"], 1200)
        self.assertEqual(started["session"], {
            "command": "start_focus", "event": "focus_started", "state": "RUNNING",
            "current_task": "背单词", "duration_seconds": 1200, "remaining_seconds": 1200,
        })

    def test_api_requires_confirmation(self):
        plan = preview_plan("背单词 20 分钟")
        with self.assertRaises(ValueError):
            start_session(plan, confirmed=False)
