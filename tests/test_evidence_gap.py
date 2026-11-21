import json
import unittest
from pathlib import Path

from eyeseeyou_edge.replay import replay
from examples.sampling_sweep import observations


class EvidenceGapTest(unittest.TestCase):
    def test_reopening_cannot_start_a_long_closure_alert(self):
        for hz in (5, 10, 20, 25, 50):
            for duration in (1400, 1490, 2000):
                with self.subTest(hz=hz, duration=duration):
                    actions = [(r["t_ms"], r["eye_state"], r["action"])
                               for r in replay(observations(hz, duration)) if r["action"]]
                    period = 1000 // hz
                    if duration < 1500:
                        self.assertEqual(actions, [])
                    else:
                        first = 10000 + ((1500 + period - 1) // period) * period
                        self.assertEqual(actions, [(first, "CLOSED", "request_fatigue_alert"),
                                                   (12000 + period, "OPEN", "clear_fatigue_alert")])

    def test_tracking_loss_does_not_bridge_perclos_windows(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "tracking_loss.jsonl"
        lines = sample.read_bytes().splitlines()
        for face_found in (True, False):
            with self.subTest(face_found=face_found):
                rows = [json.loads(line) for line in lines]
                for row in rows:
                    if row["eye_state"] == "UNCERTAIN" and not face_found:
                        row.update(face_found=False, ear=None, mar=None)
                decisions = list(replay(json.dumps(row).encode() for row in rows))
                self.assertEqual(decisions[-1]["perclos"], 0.0)
                self.assertEqual(decisions[-1]["state"], "NORMAL" if face_found else "RECOVERING")
                self.assertFalse(any(item["action"] for item in decisions))

    def test_valid_observations_still_trigger_perclos_warning(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "tracking_loss.jsonl"
        rows = sample.read_bytes().splitlines()[:5]
        for i in range(1, 81):
            closed = i % 4 in (1, 2)
            row = dict(t_ms=8000 + i * 200, face_found=True, eye_state="CLOSED" if closed else "OPEN",
                       ear=0.1 if closed else 0.3, mar=0.1)
            rows.append(json.dumps(row).encode())
        decisions = list(replay(rows))
        self.assertEqual([item["t_ms"] for item in decisions if item["action"]], [23000])
        self.assertEqual(decisions[-1]["state"], "WARNING")
        self.assertTrue(all(item["eye_closed_seconds"] < 1.5 for item in decisions))

    def test_camera_gap_then_continuous_closure(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "camera_gap.jsonl"
        rows = sample.read_bytes().splitlines()
        closed = json.loads(rows[-1])
        # The camera keeps reporting closed eyes after the first frame back.
        rows.extend(json.dumps(dict(closed, t_ms=t)).encode() for t in (12700, 13300, 14000))
        decisions = {item["t_ms"]: item for item in replay(rows)}
        self.assertEqual(decisions[9200]["eye_closed_seconds"], 0.2)
        resumed = decisions[12500]
        self.assertEqual(resumed["eye_closed_seconds"], 0.0)
        self.assertEqual(resumed["blinks_total"], 0)
        self.assertEqual(resumed["state"], "NORMAL")
        self.assertFalse(resumed["alarm"])
        self.assertIsNone(resumed["action"])
        self.assertEqual(decisions[12700]["eye_closed_seconds"], 0.2)
        self.assertEqual(decisions[14000]["eye_closed_seconds"], 1.5)
        self.assertEqual(decisions[14000]["action"], "request_fatigue_alert")

    def test_observation_gap_boundary(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "camera_gap.jsonl"
        rows = sample.read_bytes().splitlines()
        closed = json.loads(rows[-1])
        for t, expected in ((16001, 1.2), (16002, 0.0)):
            with self.subTest(t=t):
                times = (14801, 15001, t)
                frames = [json.dumps(dict(closed, t_ms=ms)).encode() for ms in times]
                decision = list(replay(rows[:5] + frames))[-1]
                self.assertEqual(decision["eye_closed_seconds"], expected)

    def test_outage_does_not_age_perclos_or_turn_an_open_mouth_into_a_yawn(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "camera_gap.jsonl"
        rows = sample.read_bytes().splitlines()[:5]
        closed = {"face_found": True, "eye_state": "CLOSED", "ear": 0.1, "mar": 0.7}
        rows.extend(json.dumps(dict(closed, t_ms=t)).encode() for t in (9000, 9200, 9400, 26000))
        resumed = list(replay(rows))[-1]
        self.assertEqual(resumed["perclos"], 0)
        self.assertEqual(resumed["reasons"], [])
        self.assertIsNone(resumed["action"])

    def test_face_loss_breaks_closure_evidence(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "fatigue.jsonl"
        calibration = sample.read_bytes().splitlines()[:5]
        rows = [
            {"t_ms": t, "face_found": present, "eye_state": "CLOSED" if present else "UNCERTAIN",
             "ear": 0.1 if present else None, "mar": 0.1 if present else None}
            for t, present in [(9000, True), (9200, True), (9300, False), (12500, True)]
        ]
        decisions = list(replay(calibration + [json.dumps(row).encode() for row in rows]))
        self.assertEqual(decisions[-2]["state"], "NO_FACE")
        self.assertEqual(decisions[-1]["eye_closed_seconds"], 0)
        self.assertFalse(decisions[-1]["alarm"])
        self.assertIsNone(decisions[-1]["action"])
