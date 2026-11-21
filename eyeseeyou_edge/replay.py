"""Replay timestamped observations through the local fatigue rules."""

import json
import math
from pathlib import Path

from .fatigue import TemporalFatigueEngine
from .models import FaceResult, VisionMetrics, VisionObservation


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate field {key!r}")
        result[key] = value
    return result


def parse_observation(line, previous_ms):
    sample = json.loads(line.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(sample, dict):
        raise ValueError("expected a JSON object")
    if set(sample) != {"t_ms", "face_found", "eye_state", "ear", "mar"}:
        raise ValueError("expected exactly t_ms, face_found, eye_state, ear, mar")
    t_ms = sample["t_ms"]
    if type(t_ms) is not int or not 0 <= t_ms <= 2**52:
        raise ValueError("t_ms must be a nonnegative integer up to 2^52")
    if previous_ms is not None and t_ms <= previous_ms:
        raise ValueError("t_ms must strictly increase")
    found = sample["face_found"]
    if type(found) is not bool:
        raise ValueError("face_found must be a boolean")
    eye_state = sample["eye_state"]
    if eye_state not in ("OPEN", "CLOSED", "UNCERTAIN"):
        raise ValueError("eye_state must be OPEN, CLOSED, or UNCERTAIN")
    ear, mar = sample["ear"], sample["mar"]
    if found:
        for name, value in (("ear", ear), ("mar", mar)):
            if type(value) not in (int, float) or value < 0 or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite nonnegative number")
    elif ear is not None or mar is not None or eye_state != "UNCERTAIN":
        raise ValueError("face_found=false requires null ear and mar and UNCERTAIN eye_state")
    observation = VisionObservation(
        face=FaceResult(found=found),
        metrics=VisionMetrics(ear=ear, mar=mar, eye_state=eye_state, eye_detector="ocec_v3"),
        source="synthetic-replay",
    )
    return t_ms, observation


def replay(source):
    """Yield one decision per UTF-8 JSONL input line (bytes), in input order."""
    config_path = Path(__file__).with_name("replay_config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    engine = TemporalFatigueEngine(config["fatigue"], config["eye_detector"])
    cooldown_ms = round(config["event_cooldown_seconds"] * 1000)
    previous_ms = first_ms = last_alert_ms = None
    active = False
    for line_number, line in enumerate(source, 1):
        try:
            t_ms, observation = parse_observation(line, previous_ms)
        except (ValueError, OverflowError, RecursionError) as exc:
            raise ValueError(f"line {line_number}: {exc}") from exc
        if first_ms is None:
            first_ms = t_ms
        previous_ms = t_ms
        state = engine.update(observation, now=(t_ms - first_ms) / 1000)

        # Record the original alert episode and cooldown as intents, with no I/O side effects.
        action = None
        if state.alarm and state.state in ("WARNING", "FATIGUE"):
            if not active and (last_alert_ms is None or t_ms - last_alert_ms >= cooldown_ms):
                action = "request_fatigue_alert"
                active = True
                last_alert_ms = t_ms
        elif active:
            action = "clear_fatigue_alert"
            active = False
        yield {
            "t_ms": t_ms,
            "state": state.state,
            "calibrated": state.calibrated,
            "eye_state": state.eye_state,
            "eye_sample_valid": state.eye_sample_valid,
            "eye_closed_seconds": round(state.eye_closed_seconds, 3),
            "blinks_total": state.blinks_total,
            "perclos": round(state.perclos, 4),
            "risk_score": state.risk_score,
            "reasons": state.reasons,
            "alarm": state.alarm,
            "action": action,
        }
    if first_ms is None:
        raise ValueError("line 1: expected at least one observation")
