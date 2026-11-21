import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


def run_replay(path, *options):
    return subprocess.run(
        [sys.executable, "-B", "-m", "eyeseeyou_edge", str(path), *options],
        cwd=ROOT,
        capture_output=True,
    )


class ReplayTest(unittest.TestCase):
    def test_offline_report_matches_replay(self):
        class ReportRows(HTMLParser):
            def __init__(self):
                super().__init__()
                self.rows = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "tr" and "id" in attrs:
                    self.rows.append((attrs["id"], attrs.get("class", "")))

        with TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "report.html"
            for name in ("fatigue", "camera_gap", "tracking_loss"):
                with self.subTest(name=name):
                    sample = ROOT / "examples" / f"{name}.jsonl"
                    expected = list(map(json.loads, run_replay(sample).stdout.splitlines()))
                    result = run_replay(sample, "--report", report)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    html = report.read_text(encoding="utf-8")
                    parsed = ReportRows()
                    parsed.feed(html)
                    self.assertEqual(parsed.rows, [
                        (f"t-{row['t_ms']}", row["action"] or "") for row in expected
                    ])
                    if name == "camera_gap":
                        self.assertIn("3300 ms", html)
                    if name == "tracking_loss":
                        self.assertIn("提醒 0 次", html)

    def test_failed_report_preserves_files(self):
        with TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "input.jsonl"
            good = (ROOT / "examples" / "fatigue.jsonl").read_bytes().splitlines()[0]
            sample.write_bytes(good + b"\n{\n")
            report = Path(temp_dir) / "report.html"
            report.write_text("previous report", encoding="utf-8")
            result = run_replay(sample, "--report", report)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"line 2", result.stderr)
            self.assertEqual(report.read_text(encoding="utf-8"), "previous report")
            before = sample.read_bytes()
            self.assertEqual(run_replay(sample, "--report", sample).returncode, 2)
            self.assertEqual(sample.read_bytes(), before)
            self.assertEqual(set(Path(temp_dir).iterdir()), {sample, report})

    def test_synthetic_replay(self):
        sample = ROOT / "examples" / "fatigue.jsonl"
        result = run_replay(sample)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run_replay(sample).stdout, result.stdout)
        decisions = {decision["t_ms"]: decision for decision in map(json.loads, result.stdout.splitlines())}
        self.assertEqual(decisions[0]["state"], "CALIBRATING")
        self.assertEqual(decisions[8000]["state"], "NORMAL")
        self.assertEqual(decisions[9400]["blinks_total"], 1)
        self.assertFalse(decisions[9400]["alarm"])
        low_quality = decisions[10200]
        self.assertFalse(low_quality["eye_sample_valid"])
        self.assertEqual(low_quality["perclos"], decisions[10000]["perclos"])
        self.assertEqual(low_quality["blinks_total"], 1)
        self.assertFalse(low_quality["alarm"])
        alert = decisions[12500]
        self.assertEqual((alert["state"], alert["eye_closed_seconds"]), ("FATIGUE", 1.5))
        self.assertEqual(
            [(item["t_ms"], item["action"]) for item in decisions.values() if item["action"]],
            [(12500, "request_fatigue_alert"), (13250, "clear_fatigue_alert")],
        )
        self.assertEqual(decisions[13500]["state"], "NORMAL")

    def test_bad_input_reports_line_and_fails(self):
        good = b'{"t_ms":0,"face_found":true,"eye_state":"OPEN","ear":0.3,"mar":0.1}\n'
        cases = (
            (good, b"strictly increase"),
            (b"{", b"Expecting"),
            (b"\xff", b"utf-8"),
            (good.replace(b'"t_ms":0', b'"t_ms":1').replace(b"0.3", b"1e999"), b"finite"),
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.jsonl"
            for bad, detail in cases:
                with self.subTest(bad=bad):
                    path.write_bytes(good + bad)
                    result = run_replay(path)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(b"line 2", result.stderr)
                    self.assertIn(detail, result.stderr)
