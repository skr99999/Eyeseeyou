from __future__ import annotations

from collections import deque
import time

from .models import FatigueState, VisionObservation


class TemporalFatigueEngine:
    """Deterministic fatigue state over timestamped visual observations."""

    def __init__(self, cfg: dict, eye_cfg: dict | None = None):
        self.cfg = cfg
        self.eye_cfg = dict(eye_cfg or {})
        self.eye_mode = str(self.eye_cfg.get("mode", "hybrid_v2"))
        self.max_observation_gap = float(cfg.get("max_observation_gap_seconds", 1.0))
        self.last_observation_at: float | None = None
        self.reset_calibration()
        self.closed_history: deque[tuple[float, bool]] = deque()
        self.blink_times: deque[float] = deque()
        self.yawn_times: deque[float] = deque()
        self.eye_closed_since: float | None = None
        self.eye_candidate_since: float | None = None
        self.mouth_open_since: float | None = None
        self.face_missing_since: float | None = None
        self.closed_candidate_frames = 0
        self.open_candidate_frames = 0
        self.eyes_closed_latched = False
        self._blink_latched = False
        self._yawn_latched = False
        self.blinks_total = 0
        self.yawns_total = 0
        self.last_state = FatigueState()

    def reset_calibration(self) -> None:
        self.calibration_started: float | None = None
        self.ear_samples: list[float] = []
        self.left_ear_samples: list[float] = []
        self.right_ear_samples: list[float] = []
        self.left_white_samples: list[float] = []
        self.right_white_samples: list[float] = []
        self.left_contrast_samples: list[float] = []
        self.right_contrast_samples: list[float] = []
        self.calibrated = False
        self.ear_threshold = float(getattr(self, "ear_threshold", 0.22))
        self.left_ear_threshold = float(getattr(self, "left_ear_threshold", self.ear_threshold))
        self.right_ear_threshold = float(getattr(self, "right_ear_threshold", self.ear_threshold))
        self.left_white_baseline = float(getattr(self, "left_white_baseline", 0.0))
        self.right_white_baseline = float(getattr(self, "right_white_baseline", 0.0))
        self.left_contrast_baseline = float(getattr(self, "left_contrast_baseline", 0.0))
        self.right_contrast_baseline = float(getattr(self, "right_contrast_baseline", 0.0))

    def reset_runtime_state(self) -> FatigueState:
        """Clear live fatigue evidence while preserving calibration and history storage."""
        self.closed_history.clear()
        self.last_observation_at = None
        self.yawn_times.clear()
        self.eye_closed_since = None
        self.eye_candidate_since = None
        self.mouth_open_since = None
        self.face_missing_since = None
        self.closed_candidate_frames = 0
        self.open_candidate_frames = 0
        self.eyes_closed_latched = False
        self._blink_latched = False
        self._yawn_latched = False
        self.yawns_total = 0
        self.last_state = FatigueState(
            state="NORMAL" if self.calibrated else "CALIBRATING",
            calibrated=self.calibrated,
            ear_threshold=self.ear_threshold,
            blinks_last_minute=len(self.blink_times),
            blinks_total=self.blinks_total,
            yawn_count=0,
            yawns_last_10_minutes=0,
            reasons=[],
            alarm=False,
        )
        return self.last_state

    def update(self, obs: VisionObservation, now: float | None = None) -> FatigueState:
        now = time.monotonic() if now is None else now
        m = obs.metrics
        valid = obs.error is None and obs.face.found and m.ear is not None and m.mar is not None
        left_ear = m.left_ear if m.left_ear is not None else m.ear
        right_ear = m.right_ear if m.right_ear is not None else m.ear
        state = FatigueState(
            state="CALIBRATING" if not self.calibrated else "NORMAL",
            face_present=valid,
            calibrated=self.calibrated,
            ear=m.ear,
            left_ear=left_ear,
            right_ear=right_ear,
            left_eye_white_ratio=m.left_eye_white_ratio,
            right_eye_white_ratio=m.right_eye_white_ratio,
            left_eye_quality=m.left_eye_quality,
            right_eye_quality=m.right_eye_quality,
            left_eye_open_probability=m.left_eye_open_probability,
            right_eye_open_probability=m.right_eye_open_probability,
            left_eye_state=m.left_eye_state,
            right_eye_state=m.right_eye_state,
            eye_state=m.eye_state,
            eye_detector=m.eye_detector,
            ear_threshold=self.ear_threshold,
            mar=m.mar,
            pitch=m.pitch,
            yaw=m.yaw,
            roll=m.roll,
        )

        # Round below the replay clock's millisecond resolution at the exact boundary.
        gap = (self.last_observation_at is not None
               and round(now - self.last_observation_at, 6) > self.max_observation_gap)
        self.last_observation_at = now
        # Frames can keep arriving while neither eye is trackable.
        if self.closed_history and round(now - self.closed_history[-1][0], 6) > self.max_observation_gap:
            self.closed_history.clear()
        if gap:
            self.face_missing_since = None
        if gap or not valid:
            self.closed_candidate_frames = self.open_candidate_frames = 0
            self.eye_candidate_since = self.eye_closed_since = self.mouth_open_since = None
            self.eyes_closed_latched = self._blink_latched = self._yawn_latched = False

        if obs.error is not None:
            state.state = "MODEL_NOT_READY"
            state.reasons = [str(obs.error.get("message", "视觉模型未就绪"))]
            state.risk_score = 0.0
            state.alarm = False
            self.last_state = state
            return state

        if not valid:
            self.face_missing_since = now if self.face_missing_since is None else self.face_missing_since
            state.face_missing_seconds = now - self.face_missing_since
            state.state = "NO_FACE" if state.face_missing_seconds < self.cfg["face_missing_warning_seconds"] else "WARNING"
            state.reasons = ["未检测到有效人脸或视觉模型未就绪"]
            state.risk_score = 0.2 if state.state == "WARNING" else 0.0
            self.last_state = state
            return state
        self.face_missing_since = None

        if not self.calibrated:
            if self.calibration_started is None:
                self.calibration_started = now
            self.ear_samples.append(float(m.ear))
            self.left_ear_samples.append(float(left_ear))
            self.right_ear_samples.append(float(right_ear))
            hybrid_cfg = self.cfg.get("eye_hybrid", {})
            min_quality = float(hybrid_cfg.get("min_quality", 0.35))
            if m.left_eye_quality is not None and m.left_eye_quality >= min_quality:
                if m.left_eye_white_ratio is not None and m.left_eye_contrast is not None:
                    self.left_white_samples.append(float(m.left_eye_white_ratio))
                    self.left_contrast_samples.append(float(m.left_eye_contrast))
            if m.right_eye_quality is not None and m.right_eye_quality >= min_quality:
                if m.right_eye_white_ratio is not None and m.right_eye_contrast is not None:
                    self.right_white_samples.append(float(m.right_eye_white_ratio))
                    self.right_contrast_samples.append(float(m.right_eye_contrast))
            elapsed = now - self.calibration_started
            state.calibration_progress = min(1.0, elapsed / self.cfg["calibration_seconds"])
            if elapsed < self.cfg["calibration_seconds"]:
                state.reasons = ["请自然睁眼并正视摄像头完成校准"]
                self.last_state = state
                return state
            self._finish_calibration()
            state.calibrated = True
            state.ear_threshold = self.ear_threshold

        classifier_active = self.eye_mode == "ocec_v3" and m.eye_detector == "ocec_v3"
        if classifier_active:
            eye_sample_valid = m.eye_state in {"OPEN", "CLOSED"}
            both_below = m.eye_state == "CLOSED"
            both_open = m.eye_state == "OPEN"
            confirm_frames = int(self.eye_cfg.get("closed_confirm_frames", 2))
            open_confirm_frames = int(self.eye_cfg.get("open_confirm_frames", 2))
        else:
            # V2/automatic degradation path. Photometry remains available only in
            # this rollback mode; OCEC never lets black/white evidence veto closure.
            geometry_both_below = (
                float(left_ear) < self.left_ear_threshold
                and float(right_ear) < self.right_ear_threshold
            )
            hybrid_cfg = self.cfg.get("eye_hybrid", {})
            left_photo_open = self._photometric_open(
                m.left_eye_white_ratio, m.left_eye_contrast, m.left_eye_quality,
                self.left_white_baseline, self.left_contrast_baseline, hybrid_cfg,
            )
            right_photo_open = self._photometric_open(
                m.right_eye_white_ratio, m.right_eye_contrast, m.right_eye_quality,
                self.right_white_baseline, self.right_contrast_baseline, hybrid_cfg,
            )
            state.hybrid_eye_active = left_photo_open is not None or right_photo_open is not None
            both_below = geometry_both_below and not (left_photo_open is True or right_photo_open is True)
            both_open = (
                float(left_ear) > self.left_ear_threshold * self.cfg["eye_open_hysteresis_ratio"]
                and float(right_ear) > self.right_ear_threshold * self.cfg["eye_open_hysteresis_ratio"]
            )
            eye_sample_valid = True
            confirm_frames = int(self.cfg["eye_state_confirm_frames"])
            open_confirm_frames = int(self.cfg.get("eye_open_confirm_frames", 1))
            if self.eye_mode == "ocec_v3":
                state.eye_detector = "ear_fallback"

        state.eye_sample_valid = eye_sample_valid
        if not eye_sample_valid:
            # Unknown samples neither extend a closure nor enter PERCLOS/blink data.
            self.closed_candidate_frames = 0
            self.open_candidate_frames = 0
            self.eye_candidate_since = None
            self.eyes_closed_latched = False
            self.eye_closed_since = None
            self._blink_latched = False
        if not self.eyes_closed_latched:
            if eye_sample_valid and both_below:
                self.closed_candidate_frames += 1
                if self.eye_candidate_since is None:
                    self.eye_candidate_since = now
                if self.closed_candidate_frames >= confirm_frames:
                    self.eyes_closed_latched = True
                    self.eye_closed_since = self.eye_candidate_since
                    self.open_candidate_frames = 0
            else:
                self.closed_candidate_frames = 0
                self.eye_candidate_since = None
        else:
            if eye_sample_valid and both_open:
                self.open_candidate_frames += 1
                if self.open_candidate_frames >= open_confirm_frames:
                    self.eyes_closed_latched = False
                    self.closed_candidate_frames = 0
                    self.eye_candidate_since = None
            else:
                self.open_candidate_frames = 0
        closed = self.eyes_closed_latched
        state.eyes_closed = closed
        if eye_sample_valid:
            self.closed_history.append((now, closed))
        cutoff = now - self.cfg["perclos_window_seconds"]
        while self.closed_history and self.closed_history[0][0] < cutoff:
            self.closed_history.popleft()
        state.perclos = sum(v for _, v in self.closed_history) / max(1, len(self.closed_history))

        if closed:
            self.eye_closed_since = now if self.eye_closed_since is None else self.eye_closed_since
            state.eye_closed_seconds = now - self.eye_closed_since
            if state.eye_closed_seconds >= self.cfg["blink_min_seconds"]:
                self._blink_latched = True
        else:
            if self._blink_latched:
                self.blinks_total += 1
                self.blink_times.append(now)
            self._blink_latched = False
            self.eye_closed_since = None

        state.mouth_open = float(m.mar) >= self.cfg["mar_threshold"]
        if state.mouth_open:
            self.mouth_open_since = now if self.mouth_open_since is None else self.mouth_open_since
            if now - self.mouth_open_since >= self.cfg["yawn_min_seconds"] and not self._yawn_latched:
                self.yawns_total += 1
                self.yawn_times.append(now)
                self._yawn_latched = True
        else:
            self.mouth_open_since = None
            self._yawn_latched = False

        while self.blink_times and self.blink_times[0] < now - 60.0:
            self.blink_times.popleft()
        while self.yawn_times and self.yawn_times[0] < now - 600.0:
            self.yawn_times.popleft()
        state.blinks_last_minute = len(self.blink_times)
        state.blinks_total = self.blinks_total
        state.yawn_count = self.yawns_total
        state.yawns_last_10_minutes = len(self.yawn_times)

        reasons: list[str] = []
        risk = 0.0
        if state.eye_closed_seconds >= self.cfg["long_eye_closure_seconds"]:
            reasons.append(f"持续闭眼 {state.eye_closed_seconds:.1f}s")
            risk += 0.75
        observed = self.closed_history[-1][0] - self.closed_history[0][0] if len(self.closed_history) > 1 else 0.0
        if observed >= self.cfg["perclos_min_observation_seconds"] and state.perclos >= self.cfg["perclos_warning_threshold"]:
            reasons.append(f"PERCLOS偏高 {state.perclos:.0%}")
            risk += 0.55
        if self.mouth_open_since is not None and now - self.mouth_open_since >= self.cfg["yawn_min_seconds"]:
            reasons.append("检测到哈欠")
            risk += 0.3
        if state.yawns_last_10_minutes >= self.cfg["frequent_yawn_count"]:
            reasons.append("短时间内多次哈欠")
            risk += 0.25

        state.risk_score = min(1.0, risk)
        state.reasons = reasons
        if risk >= 0.75:
            state.state, state.alarm = "FATIGUE", True
        elif risk >= 0.45:
            state.state, state.alarm = "WARNING", True
        elif reasons:
            state.state = "SUSPECTED"
        elif self.last_state.state in {"WARNING", "FATIGUE"}:
            state.state = "RECOVERING"
        else:
            state.state = "NORMAL"
        self.last_state = state
        return state

    def _finish_calibration(self) -> None:
        self.left_ear_threshold = self._eye_threshold(self.left_ear_samples)
        self.right_ear_threshold = self._eye_threshold(self.right_ear_samples)
        self.ear_threshold = (self.left_ear_threshold + self.right_ear_threshold) / 2.0
        self.left_white_baseline = self._median_or_zero(self.left_white_samples)
        self.right_white_baseline = self._median_or_zero(self.right_white_samples)
        self.left_contrast_baseline = self._median_or_zero(self.left_contrast_samples)
        self.right_contrast_baseline = self._median_or_zero(self.right_contrast_samples)
        self.calibrated = True
        self.ear_samples.clear()
        self.left_ear_samples.clear()
        self.right_ear_samples.clear()
        self.left_white_samples.clear()
        self.right_white_samples.clear()
        self.left_contrast_samples.clear()
        self.right_contrast_samples.clear()

    def _eye_threshold(self, samples: list[float]) -> float:
        ordered = sorted(samples)
        baseline = ordered[int(len(ordered) * 0.7)]
        return min(
            self.cfg["max_ear_threshold"],
            max(self.cfg["min_ear_threshold"], baseline * self.cfg["ear_threshold_ratio"]),
        )

    @staticmethod
    def _median_or_zero(samples: list[float]) -> float:
        if not samples:
            return 0.0
        ordered = sorted(samples)
        return ordered[len(ordered) // 2]

    @staticmethod
    def _photometric_open(
        white_ratio: float | None, contrast: float | None, quality: float | None,
        white_baseline: float, contrast_baseline: float, cfg: dict,
    ) -> bool | None:
        if not cfg.get("enabled", False):
            return None
        if white_ratio is None or contrast is None or quality is None:
            return None
        if quality < float(cfg.get("min_quality", 0.35)):
            return None
        if white_baseline <= 0.0 or contrast_baseline <= 0.0:
            return None
        white_threshold = max(
            float(cfg.get("minimum_white_ratio", 0.04)),
            white_baseline * float(cfg.get("white_open_ratio", 0.62)),
        )
        contrast_threshold = contrast_baseline * float(cfg.get("contrast_open_ratio", 0.55))
        return float(white_ratio) >= white_threshold and float(contrast) >= contrast_threshold
