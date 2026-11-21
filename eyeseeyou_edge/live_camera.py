"""Windows webcam observations. Raw frames stay in memory and are never recorded."""

from collections import deque
from contextlib import ExitStack
from dataclasses import dataclass
import json
from math import dist
import os
from pathlib import Path
import sys
from threading import Event, Thread
import time

from .fatigue import TemporalFatigueEngine
from .models import FaceResult, FatigueState, VisionMetrics, VisionObservation


def model_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "models"
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "EyeSeeYou Edge" / "models"


def face_metrics(points):
    def eye(a, b, c, d, e, f):
        width = dist(points[a], points[d])
        if width < 8:
            return None
        return (dist(points[b], points[f]) + dist(points[c], points[e])) / (2 * width)

    left = eye(33, 160, 158, 133, 153, 144)
    right = eye(362, 385, 387, 263, 373, 380)
    mouth = dist(points[78], points[308])
    if left is None or right is None or mouth < 8:
        return VisionMetrics()
    return VisionMetrics(ear=(left + right) / 2, left_ear=left, right_ear=right,
                         mar=dist(points[13], points[14]) / mouth, eye_detector="face_landmarks")


def hand_pose(points, category, score):
    # The canned classifier includes palm and fist. OK additionally needs a pinch
    # and at least two extended fingers, to distinguish it from a closed fist.
    scale = dist(points[0], points[9])
    extended = sum(dist(points[tip], points[0]) > 1.18 * dist(points[tip-2], points[0])
                   for tip in (12, 16, 20))
    if scale > 0 and dist(points[4], points[8]) < .30 * scale and extended >= 2:
        return "OK"
    if category == "Open_Palm" and score >= .6:
        return "OPEN_PALM"
    if category == "Closed_Fist" and score >= .7:
        return "FIST"
    return ""


class GestureHold:
    def __init__(self):
        self.pose = ""
        self.start = self.previous = self.last_fire = -1e9
        self.frames = 0
        self.fired = False

    def update(self, pose, now):
        if pose != self.pose or now-self.previous > .45:
            self.pose, self.start, self.frames, self.fired = pose, now, 0, False
        self.previous = now
        self.frames += 1
        if pose and not self.fired and self.frames >= 5 and now-self.start >= .8 and now-self.last_fire >= 2:
            self.fired, self.last_fire = True, now
            return pose
        return ""


@dataclass
class LiveFrame:
    number: int
    captured: float
    ppm: bytes
    state: FatigueState
    pose: str
    width: int
    height: int


class CameraSession:
    def __init__(self):
        self.stopping = Event()
        self.frames = deque(maxlen=1)
        self.size = (400, 240)
        self.error = ""
        self.thread = Thread(target=self._run, daemon=True, name="EyeSeeYou camera")

    def _run(self):
        try:
            import cv2
            import mediapipe as mp

            vision = mp.tasks.vision
            folder = model_directory()
            config = json.loads(Path(__file__).with_name("replay_config.json").read_text("utf-8"))
            engine = TemporalFatigueEngine(config["fatigue"])
            with ExitStack() as stack:
                def options(name):
                    path = folder / (name + ".task")
                    if not path.is_file():
                        raise FileNotFoundError(f"缺少模型 {path.name}，请安装完整摄像头版。")
                    return mp.tasks.BaseOptions(model_asset_buffer=path.read_bytes())

                face = stack.enter_context(vision.FaceLandmarker.create_from_options(
                    vision.FaceLandmarkerOptions(base_options=options("face_landmarker"),
                                                 running_mode=vision.RunningMode.VIDEO)))
                hand = stack.enter_context(vision.GestureRecognizer.create_from_options(
                    vision.GestureRecognizerOptions(base_options=options("gesture_recognizer"),
                                                    running_mode=vision.RunningMode.VIDEO)))
                if self.stopping.is_set():
                    return
                cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                stack.callback(cam.release)
                if not cam.isOpened():
                    raise OSError("无法打开默认摄像头，请检查相机权限和占用情况。")
                cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                number, last_ms = 0, -1
                while not self.stopping.is_set():
                    ok, bgr = cam.read()
                    if not ok:
                        raise OSError("摄像头已断流，请重新打开。")
                    now = time.monotonic()
                    stamp = max(last_ms+1, int(now*1000))
                    last_ms = stamp
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    h, w = rgb.shape[:2]
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    faces = face.detect_for_video(image, stamp).face_landmarks
                    hands = hand.recognize_for_video(image, stamp)
                    metrics = VisionMetrics()
                    if faces:
                        points = [(p.x*w, p.y*h) for p in faces[0]]
                        metrics = face_metrics(points)
                        for i in (33, 133, 362, 263):
                            cv2.circle(rgb, tuple(map(round, points[i])), 2, (48, 221, 212), -1)
                    pose = ""
                    if hands.hand_landmarks and hands.gestures and hands.gestures[0]:
                        points = [(p.x*w, p.y*h) for p in hands.hand_landmarks[0]]
                        cat = hands.gestures[0][0]
                        pose = hand_pose(points, cat.category_name, cat.score)
                        for i in (0, 4, 8, 12, 16, 20):
                            cv2.circle(rgb, tuple(map(round, points[i])), 3, (255, 190, 74), -1)
                    obs = VisionObservation(face=FaceResult(found=bool(faces)), metrics=metrics, source="webcam")
                    if not engine.calibrated and engine.calibration_started is not None and (
                        metrics.ear is None or now-engine.last_observation_at > engine.max_observation_gap
                    ):
                        engine.reset_calibration()
                    state = engine.update(obs, now)
                    tw, th = self.size
                    ratio = min(tw/w, th/h, 1)
                    preview = cv2.flip(cv2.resize(rgb, (max(1,round(w*ratio)), max(1,round(h*ratio)))), 1)
                    ph, pw = preview.shape[:2]
                    ppm = f"P6\n{pw} {ph}\n255\n".encode() + preview.tobytes()
                    number += 1
                    self.frames.append(LiveFrame(number, now, ppm, state, pose, w, h))
        except Exception as error:
            self.error = str(error) or type(error).__name__
