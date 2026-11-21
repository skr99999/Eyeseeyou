import json
from pathlib import Path
import unittest

from eyeseeyou_edge.fatigue import TemporalFatigueEngine
from eyeseeyou_edge.live_camera import face_metrics, GestureHold, hand_pose
from eyeseeyou_edge.models import FaceResult, VisionObservation


class LiveCameraTest(unittest.TestCase):
    def test_open_then_closed_geometry_and_camera_gap(self):
        config = json.loads((Path(__file__).resolve().parents[1] / "eyeseeyou_edge/replay_config.json").read_text())
        engine = TemporalFatigueEngine(config["fatigue"])
        def observation(gap):
            points = [(0, 0)] * 478
            for ids in [(33,160,158,133,153,144), (362,385,387,263,373,380)]:
                for i, xy in zip(ids, ((0,0),(8,-gap),(14,-gap),(24,0),(14,gap),(8,gap))):
                    points[i] = xy
            points[78], points[308] = (0,0), (30,0)
            return VisionObservation(face=FaceResult(found=True), metrics=face_metrics(points))

        opened, closed = observation(4), observation(.6)
        for i in range(91):
            state = engine.update(opened, i/10)
        self.assertTrue(state.calibrated)
        self.assertFalse(state.alarm)
        engine.update(closed, 9.1)
        self.assertFalse(engine.update(closed, 14).alarm)
        for i in range(141, 159):
            state = engine.update(closed, i/10)
        self.assertTrue(state.alarm)
        for i in range(159, 163):
            state = engine.update(opened, i/10)
        self.assertFalse(state.alarm)
        self.assertIsNone(face_metrics([(0,0)] * 478).ear)

    def test_pinch_and_canned_gestures(self):
        points = [(0,0)] * 21
        points[9] = (0,10)
        points[4], points[8] = (5,16), (6,17)
        for finger in (12,16,20):
            points[finger-2], points[finger] = (0,15), (0,22)
        self.assertEqual(hand_pose(points, "None", .9), "OK")
        points[4] = (-10, 10)
        self.assertEqual(hand_pose(points, "Closed_Fist", .9), "FIST")
        self.assertEqual(hand_pose(points, "Open_Palm", .9), "OPEN_PALM")
        self.assertEqual(hand_pose(points, "Open_Palm", .35), "")

    def test_one_action_per_hold_and_no_action_across_outage(self):
        hold = GestureHold()
        events = [hold.update("OK", i/10) for i in range(30)]
        self.assertEqual([e for e in events if e], ["OK"])
        hold.update("", 3.0)
        for i in range(31, 36):
            self.assertFalse(hold.update("FIST", i/10))
        self.assertFalse(hold.update("FIST", 7))
        events = [hold.update("FIST", 7+i/10) for i in range(1, 14)]
        self.assertEqual([e for e in events if e], ["FIST"])
