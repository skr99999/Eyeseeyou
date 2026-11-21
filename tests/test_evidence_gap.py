import json
import unittest
from pathlib import Path

from eyeseeyou_edge.__main__ import replay


class EvidenceGapTest(unittest.TestCase):
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
