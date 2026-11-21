from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from eyeseeyou_edge.database import Database
from eyeseeyou_edge.focus import FocusSessionController
from eyeseeyou_edge.plan import confirm_plan, preview_plan


class DesktopSessionTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows desktop UI")
    def test_preview_confirmation_pause_and_export(self):
        import tkinter as tk
        from eyeseeyou_edge.desktop import Desktop

        with TemporaryDirectory() as temp:
            db = Database(Path(temp) / "study.sqlite")
            root = tk.Tk()
            root.withdraw()
            app = Desktop(root, db)
            try:
                app.primary.invoke()
                self.assertEqual(app.focus.current.state, "IDLE")
                self.assertIn("回忆测试", app.outline.cget("text"))
                app.goal.set("读书 1 分钟")
                self.assertIsNone(app.plan)
                app.primary.invoke()
                app.primary.invoke()
                self.assertEqual(app.focus.current.state, "RUNNING")
                app.primary.invoke()
                self.assertEqual(app.focus.current.state, "PAUSED")
                app.primary.invoke()
                self.assertEqual(app.focus.current.state, "RUNNING")
                app.select(Path(__file__).resolve().parents[1] / "examples" / "fatigue.jsonl")
                target = Path(temp) / "report.html"
                with patch("tkinter.filedialog.asksaveasfilename", return_value=str(target)):
                    app.export.invoke()
                app.job.result(timeout=10)
                app.check_export()
                self.assertTrue(app.open_report.instate(["!disabled"]))
                self.assertIn("发出提醒 1 次", target.read_text("utf-8"))
            finally:
                app.close()
                db.conn.close()

    def test_manual_clock_resume_and_stop_during_review(self):
        with TemporaryDirectory() as temp:
            database = Database(Path(temp) / "sessions.sqlite")
            try:
                controller = FocusSessionController({}, database)
                request = confirm_plan(preview_plan("读书 1 分钟"), confirmed=True)
                controller.command(request["command"], request["payload"], now=1)
                for t in range(1, 42):
                    controller.update(None, now=t)
                self.assertEqual(controller.current.state, "RUNNING")
                self.assertEqual(controller.current.remaining_seconds, 20)
                controller.checkpoint(now=41, force=True)
                restored = FocusSessionController({}, database)
                self.assertEqual(restored.current.state, "PAUSED")
                restored.command("resume_focus", now=50)
                for t in range(50, 71):
                    restored.update(None, now=t)
                self.assertTrue(restored.current.segment_review_ready)
                restored.command("stop_focus", now=71)
                restored.command(request["command"], request["payload"], now=72)
                self.assertEqual(restored.current.state, "RUNNING")
            finally:
                database.conn.close()
