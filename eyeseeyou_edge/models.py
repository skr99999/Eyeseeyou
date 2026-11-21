from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class FrameInfo:
    sequence: int = 0
    captured_at: str = ""
    width: int = 0
    height: int = 0
    age_ms: float | None = None


@dataclass(frozen=True)
class FaceResult:
    found: bool = False
    confidence: float = 0.0
    bbox: list[int] | None = None
    landmarks: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class ObjectDetection:
    found: bool = False
    confidence: float = 0.0
    bbox: list[int] | None = None
    near_primary_user: bool = False
    continuous_seconds: float = 0.0
    source: str = ""
    tracked: bool = False
    evidence_count: int = 0
    evidence_sources: list[str] = field(default_factory=list)
    last_seen_age_ms: float | None = None
    candidate_count: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    confirmation_deferred: bool = False
    defer_reason: str = ""
    corroborating_sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VisionDetections:
    person: ObjectDetection = field(default_factory=ObjectDetection)
    phone: ObjectDetection = field(default_factory=ObjectDetection)
    body_roi: list[int] | None = None
    hand_roi: list[int] | None = None


@dataclass(frozen=True)
class GestureResult:
    name: str = "NONE"
    confidence: float = 0.0
    hand_score: float = 0.0
    stable: bool = False
    stable_frames: int = 0
    backend: str = "disabled"
    landmarks: list[list[float]] = field(default_factory=list)
    palm_score: float = 0.0
    tracking: bool = False
    palm_bbox: list[int] | None = None
    hand_roi: list[int] | None = None


@dataclass(frozen=True)
class VisionMetrics:
    ear: float | None = None
    left_ear: float | None = None
    right_ear: float | None = None
    left_eye_white_ratio: float | None = None
    right_eye_white_ratio: float | None = None
    left_eye_dark_ratio: float | None = None
    right_eye_dark_ratio: float | None = None
    left_eye_contrast: float | None = None
    right_eye_contrast: float | None = None
    left_eye_quality: float | None = None
    right_eye_quality: float | None = None
    left_eye_open_probability: float | None = None
    right_eye_open_probability: float | None = None
    left_eye_state: str = "UNCERTAIN"
    right_eye_state: str = "UNCERTAIN"
    eye_state: str = "UNCERTAIN"
    eye_detector: str = "hybrid_v2"
    mar: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    roll: float | None = None


@dataclass(frozen=True)
class VisionObservation:
    schema_version: str = "1.0"
    frame: FrameInfo = field(default_factory=FrameInfo)
    face: FaceResult = field(default_factory=FaceResult)
    detections: VisionDetections = field(default_factory=VisionDetections)
    gesture: GestureResult = field(default_factory=GestureResult)
    metrics: VisionMetrics = field(default_factory=VisionMetrics)
    timing: dict[str, float | None] = field(default_factory=dict)
    source: str = "torq-jsonl"
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "VisionObservation":
        frame = raw.get("frame") or {}
        face = raw.get("face") or {}
        metrics = raw.get("metrics") or {}
        detections = raw.get("detections") or {}
        person = detections.get("person") or {}
        phone = detections.get("phone") or {}
        gesture = raw.get("gesture") or {}
        return cls(
            schema_version=str(raw.get("schema_version", "1.0")),
            frame=FrameInfo(
                sequence=int(frame.get("sequence", 0)),
                captured_at=str(frame.get("captured_at", "")),
                width=int(frame.get("width", 0)),
                height=int(frame.get("height", 0)),
                age_ms=_optional_float(frame.get("age_ms")),
            ),
            face=FaceResult(
                found=bool(face.get("found", False)),
                confidence=float(face.get("confidence", 0.0)),
                bbox=face.get("bbox"),
                landmarks=list(face.get("landmarks") or []),
            ),
            detections=VisionDetections(
                person=_object_detection(person),
                phone=_object_detection(phone),
                body_roi=detections.get("body_roi"),
                hand_roi=detections.get("hand_roi"),
            ),
            gesture=GestureResult(
                name=str(gesture.get("name", "NONE")),
                confidence=float(gesture.get("confidence", 0.0)),
                hand_score=float(gesture.get("hand_score", 0.0)),
                stable=bool(gesture.get("stable", False)),
                stable_frames=int(gesture.get("stable_frames", 0)),
                backend=str(gesture.get("backend", "disabled")),
                landmarks=list(gesture.get("landmarks") or []),
                palm_score=float(gesture.get("palm_score", 0.0)),
                tracking=bool(gesture.get("tracking", False)),
                palm_bbox=gesture.get("palm_bbox"),
                hand_roi=gesture.get("hand_roi"),
            ),
            metrics=VisionMetrics(
                ear=_optional_float(metrics.get("ear")),
                left_ear=_optional_float(metrics.get("left_ear")),
                right_ear=_optional_float(metrics.get("right_ear")),
                left_eye_white_ratio=_optional_float(metrics.get("left_eye_white_ratio")),
                right_eye_white_ratio=_optional_float(metrics.get("right_eye_white_ratio")),
                left_eye_dark_ratio=_optional_float(metrics.get("left_eye_dark_ratio")),
                right_eye_dark_ratio=_optional_float(metrics.get("right_eye_dark_ratio")),
                left_eye_contrast=_optional_float(metrics.get("left_eye_contrast")),
                right_eye_contrast=_optional_float(metrics.get("right_eye_contrast")),
                left_eye_quality=_optional_float(metrics.get("left_eye_quality")),
                right_eye_quality=_optional_float(metrics.get("right_eye_quality")),
                left_eye_open_probability=_optional_float(metrics.get("left_eye_open_probability")),
                right_eye_open_probability=_optional_float(metrics.get("right_eye_open_probability")),
                left_eye_state=str(metrics.get("left_eye_state", "UNCERTAIN")),
                right_eye_state=str(metrics.get("right_eye_state", "UNCERTAIN")),
                eye_state=str(metrics.get("eye_state", "UNCERTAIN")),
                eye_detector=str(metrics.get("eye_detector", "hybrid_v2")),
                mar=_optional_float(metrics.get("mar")),
                pitch=_optional_float(metrics.get("pitch")),
                yaw=_optional_float(metrics.get("yaw")),
                roll=_optional_float(metrics.get("roll")),
            ),
            timing=dict(raw.get("timing") or {}),
            source=str(raw.get("source", "torq-jsonl")),
            error=raw.get("error"),
        )


@dataclass
class FatigueState:
    state: str = "STARTING"
    risk_score: float = 0.0
    face_present: bool = False
    calibrated: bool = False
    calibration_progress: float = 0.0
    ear: float | None = None
    left_ear: float | None = None
    right_ear: float | None = None
    left_eye_white_ratio: float | None = None
    right_eye_white_ratio: float | None = None
    left_eye_quality: float | None = None
    right_eye_quality: float | None = None
    hybrid_eye_active: bool = False
    left_eye_open_probability: float | None = None
    right_eye_open_probability: float | None = None
    left_eye_state: str = "UNCERTAIN"
    right_eye_state: str = "UNCERTAIN"
    eye_state: str = "UNCERTAIN"
    eye_detector: str = "hybrid_v2"
    eye_sample_valid: bool = False
    ear_threshold: float = 0.22
    mar: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    roll: float | None = None
    eyes_closed: bool = False
    eye_closed_seconds: float = 0.0
    blinks_last_minute: int = 0
    blinks_total: int = 0
    perclos: float = 0.0
    mouth_open: bool = False
    yawn_count: int = 0
    yawns_last_10_minutes: int = 0
    head_down: bool = False
    head_down_seconds: float = 0.0
    face_missing_seconds: float = 0.0
    reasons: list[str] = field(default_factory=list)
    alarm: bool = False
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentEvent:
    event_id: str
    type: str
    severity: str
    started_at: str
    duration_seconds: float
    evidence: dict[str, Any]
    action: str
    acknowledged: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _object_detection(raw: dict) -> ObjectDetection:
    return ObjectDetection(
        found=bool(raw.get("found", False)),
        confidence=float(raw.get("confidence", 0.0)),
        bbox=raw.get("bbox"),
        near_primary_user=bool(raw.get("near_primary_user", False)),
        continuous_seconds=float(raw.get("continuous_seconds", 0.0)),
        source=str(raw.get("source", "")),
        tracked=bool(raw.get("tracked", False)),
        evidence_count=int(raw.get("evidence_count", 0)),
        evidence_sources=[str(value) for value in (raw.get("evidence_sources") or [])],
        last_seen_age_ms=_optional_float(raw.get("last_seen_age_ms")),
        candidate_count=int(raw.get("candidate_count", 0)),
        candidates=[dict(value) for value in (raw.get("candidates") or [])],
        confirmation_deferred=bool(raw.get("confirmation_deferred", False)),
        defer_reason=str(raw.get("defer_reason", "")),
        corroborating_sources=[str(value) for value in (
            raw.get("corroborating_sources") or []
        )],
    )
