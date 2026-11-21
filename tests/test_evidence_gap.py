import json
import unittest
from pathlib import Path

from eyeseeyou_edge.__main__ import replay


class EvidenceGapTest(unittest.TestCase):
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
