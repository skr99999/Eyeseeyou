from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import time
import uuid

from .models import VisionObservation, iso_now


@dataclass
class FocusState:
    state: str = "IDLE"
    session_id: str | None = None
    duration_seconds: float = 1500.0
    remaining_seconds: float = 1500.0
    focused_seconds: float = 0.0
    paused_seconds: float = 0.0
    away_seconds: float = 0.0
    away_count: int = 0
    phone_reminders: int = 0
    phone_usage_seconds: float = 0.0
    help_count: int = 0
    current_task: str = ""
    plan: dict | None = None
    do_not_disturb: bool = False
    return_confirmation_required: bool = False
    away_started_at: str | None = None
    current_away_seconds: float = 0.0
    recovery_ready: bool = False
    recovery_id: str | None = None
    skipped_module_indices: list[int] = field(default_factory=list)
    segment_review_ready: bool = False
    segment_review_id: str | None = None
    segment_review_index: int | None = None
    segment_results: list[dict] = field(default_factory=list)
    last_action: str = "等待开始专注"
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict:
        value = asdict(self)
        value["remaining_seconds"] = round(max(0.0, self.remaining_seconds), 1)
        value["focused_seconds"] = round(self.focused_seconds, 1)
        value["paused_seconds"] = round(self.paused_seconds, 1)
        value["away_seconds"] = round(self.away_seconds, 1)
        value["phone_usage_seconds"] = round(self.phone_usage_seconds, 1)
        value["phone_usage_count"] = self.phone_reminders
        value["current_away_seconds"] = round(self.current_away_seconds, 1)
        return value


class FocusSessionController:
    """Deterministic focus state machine driven by gestures and observations."""

    def __init__(self, cfg: dict, database):
        self.cfg = cfg
        self.db = database
        duration = float(cfg.get("duration_seconds", 25 * 60))
        self.current = FocusState(duration_seconds=duration, remaining_seconds=duration)
        self.last_update = time.monotonic()
        self.last_checkpoint = self.last_update
        self.face_missing_since: float | None = None
        self.face_returned_since: float | None = None
        self.phone_since: float | None = None
        self.phone_last_seen: float | None = None
        self.phone_episode_seconds = 0.0
        self.phone_latched = False
        self.gesture_latch: str | None = None
        self.last_gesture_at = -1e9
        self._restore_latest_session()

    def update(self, observation: VisionObservation | None, now: float | None = None) -> list[dict]:
        """Advance the session clock. A manual timer can tick without visual observations."""
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, min(now - self.last_update, 2.0))
        self.last_update = now
        events: list[dict] = []

        if self.current.state == "RUNNING":
            consumed = min(elapsed, self.current.remaining_seconds)
            previous_elapsed = max(0.0, self.current.duration_seconds - self.current.remaining_seconds)
            boundary = self._next_module_boundary(previous_elapsed)
            if boundary and previous_elapsed < boundary["end_seconds"] <= previous_elapsed + consumed:
                consumed = max(0.0, boundary["end_seconds"] - previous_elapsed)
                self.current.focused_seconds += consumed
                self.current.remaining_seconds = max(0.0, self.current.remaining_seconds - consumed)
                events.append(self._prompt_segment_review(boundary))
            else:
                self.current.focused_seconds += consumed
                self.current.remaining_seconds = max(0.0, self.current.remaining_seconds - consumed)
        elif self.current.state == "PAUSED":
            self.current.paused_seconds += elapsed
        elif self.current.state == "AWAY":
            self.current.away_seconds += elapsed
            self.current.current_away_seconds += elapsed

        if observation is None:
            self.face_missing_since = self.face_returned_since = None
        elif self.current.state == "RUNNING":
            if observation.face.found:
                self.face_missing_since = None
            else:
                self.face_missing_since = self.face_missing_since or now
                if now - self.face_missing_since >= float(self.cfg.get("away_seconds", 30.0)):
                    events.append(self._enter_away())

        if observation is not None and self.current.state == "AWAY":
            if observation.face.found:
                self.face_returned_since = self.face_returned_since or now
                if (not self.current.recovery_ready and
                        now - self.face_returned_since >= float(self.cfg.get("return_stable_seconds", 2.0))):
                    events.append(self._prepare_recovery("return_detected"))
            else:
                self.face_returned_since = None

        phone_detected = (
            self.current.state == "RUNNING"
            and observation is not None
            and observation.detections.phone.found
            and observation.detections.phone.near_primary_user
        )
        if phone_detected:
            if self.phone_since is None:
                self.phone_since = now
                self.phone_episode_seconds = 0.0
            self.phone_last_seen = now
        release_seconds = float(self.cfg.get("phone_release_seconds", 2.0))
        phone_active = (
            self.current.state == "RUNNING"
            and self.phone_since is not None
            and self.phone_last_seen is not None
            and now - self.phone_last_seen <= release_seconds
        )
        if phone_active:
            self.phone_episode_seconds += elapsed
            self.current.phone_usage_seconds += elapsed
            held = now - self.phone_since
            if held >= float(self.cfg.get("phone_hold_seconds", 3.0)) and not self.phone_latched:
                self.phone_latched = True
                self.current.phone_reminders += 1
                events.append(self._event("phone_usage", {
                    "occurrence": self.current.phone_reminders,
                    "continuous_seconds": round(held, 1),
                    "total_seconds": round(self.current.phone_usage_seconds, 1),
                }))
                self.current.last_action = "已记录手机使用并提醒"
        elif self.phone_since is not None:
            if self.phone_latched:
                events.append(self._event("phone_usage_ended", {
                    "occurrence": self.current.phone_reminders,
                    "duration_seconds": round(self.phone_episode_seconds, 1),
                    "total_seconds": round(self.current.phone_usage_seconds, 1),
                }))
                self.current.last_action = "本次手机使用已结束并记录时长"
            self.phone_since = None
            self.phone_last_seen = None
            self.phone_episode_seconds = 0.0
            self.phone_latched = False

        gesture = observation.gesture if observation is not None else None
        if gesture is not None and gesture.stable and gesture.name not in {"", "NONE", "UNCERTAIN"}:
            if self.gesture_latch != gesture.name and now - self.last_gesture_at >= float(self.cfg.get("gesture_cooldown_seconds", 2.0)):
                self.gesture_latch = gesture.name
                self.last_gesture_at = now
                command = "resolve_segment" if (
                    gesture.name == "OK" and self.current.segment_review_ready
                ) else ("confirm_return" if (
                    gesture.name == "OK" and self.current.return_confirmation_required
                ) else self._gesture_command(gesture.name))
                gesture_payload = {"source": "gesture"}
                if command == "resolve_segment":
                    gesture_payload["completed"] = True
                result = self.command(command, gesture_payload, now)
                if result.get("event"):
                    events.append(result["event"])
        else:
            self.gesture_latch = None

        if self.current.state == "RUNNING" and self.current.remaining_seconds <= 0:
            events.append(self._finish("COMPLETED", "focus_completed"))
        self.current.updated_at = iso_now()
        self.checkpoint(now)
        return events

    def command(self, name: str, payload: dict | None = None, now: float | None = None) -> dict:
        payload = payload or {}
        now = time.monotonic() if now is None else now
        event = None
        if name == "resolve_recovery":
            return self._resolve_recovery(str(payload.get("action", "")), payload, now)
        if name == "resolve_segment":
            return self._resolve_segment(bool(payload.get("completed")), payload, now)
        if name == "cancel_plan":
            return self._cancel_plan(payload, now)
        if name in {"start_focus", "resume_focus"}:
            if self.current.segment_review_ready:
                return {"ok": True, "ignored": True, "reason": "请先确认本段完成情况", "state": self.status()}
            if self.current.state in {"IDLE", "COMPLETED", "STOPPED"}:
                restarted = name == "resume_focus" and self.current.state == "STOPPED" and self._restart_plan_module()
                if restarted:
                    event = restarted
                else:
                    duration = float(payload.get("duration_seconds", self.cfg.get("duration_seconds", 1500.0)))
                    if "duration_seconds" in payload and (
                        not math.isfinite(duration) or not 60.0 <= duration <= 180 * 60.0
                    ):
                        raise ValueError("专注时长必须在 1 到 180 分钟之间")
                    self.current = FocusState(
                        state="RUNNING", session_id="focus_" + uuid.uuid4().hex[:12],
                        duration_seconds=duration, remaining_seconds=duration,
                        current_task=str(payload.get("current_task") or payload.get("task") or "").strip()[:200],
                        plan=payload.get("plan"),
                        last_action="专注会话已开始",
                    )
                    self.db.start_focus_session(self.current)
                    event = self._event("focus_started", {"duration_seconds": duration})
            elif self.current.state in {"PAUSED", "AWAY"}:
                if self.current.return_confirmation_required:
                    if not self.current.recovery_ready:
                        return {"ok": True, "ignored": True, "reason": "等待稳定检测到用户返回", "state": self.status()}
                    return self._resolve_recovery("continue", payload, now)
                event = self._transition("RUNNING", "focus_resumed", "专注会话已继续")
                self.face_missing_since = None
        elif name == "pause_focus" and self.current.state == "RUNNING":
            event = self._transition("PAUSED", "focus_paused", "专注会话已暂停")
        elif name == "stop_focus" and self.current.state in {"RUNNING", "PAUSED", "AWAY"}:
            event = self._finish("STOPPED", "focus_stopped")
        elif name == "toggle_do_not_disturb":
            self.current.do_not_disturb = not self.current.do_not_disturb
            self.current.last_action = "免打扰已开启" if self.current.do_not_disturb else "免打扰已关闭"
            event = self._event("do_not_disturb", {"enabled": self.current.do_not_disturb})
        elif name == "open_help":
            self.current.help_count += 1
            modes = (
                ("hint", "提示", "请先给我解题提示，不要直接给出答案。题目是："),
                ("explain", "分步讲解", "请分步骤讲解下面题目，并说明关键知识点。题目是："),
                ("example", "相似例题", "请根据下面题目或知识点给我一道相似例题，并在我作答后再讲解。内容是："),
            )
            mode, label, prompt = modes[(self.current.help_count - 1) % len(modes)]
            self.current.last_action = f"已打开Agent求助：{label}模式"
            event = self._event("help_requested", {
                "help_count": self.current.help_count,
                "help_mode": mode,
                "help_label": label,
                "suggested_prompt": prompt,
            })
        elif name == "confirm_return":
            if not self.current.recovery_ready:
                return {"ok": True, "ignored": True, "reason": "等待稳定检测到用户返回", "state": self.status()}
            return self._resolve_recovery("continue", payload, now)
        else:
            return {"ok": False, "ignored": True, "state": self.current.to_dict()}
        self.current.updated_at = iso_now()
        if self.current.session_id:
            self.db.update_focus_session(self.current)
        return {"ok": True, "event": event, "state": self.status()}

    def _cancel_plan(self, payload: dict, now: float) -> dict:
        if not isinstance(self.current.plan, dict) or not self.current.plan.get("subtasks"):
            return {"ok": True, "ignored": True, "reason": "当前没有学习计划", "state": self.status()}
        previous = self.current
        previous_state = previous.state
        evidence = {
            "task": previous.current_task or str(previous.plan.get("task") or "学习"),
            "previous_state": previous_state,
            "remaining_seconds": round(previous.remaining_seconds, 1),
            "source": str(payload.get("source") or "web"),
        }
        previous.last_action = "学习计划已取消"
        if previous.session_id and previous_state in {"RUNNING", "PAUSED", "AWAY"}:
            previous.state = "CANCELLED"
            previous.return_confirmation_required = False
            previous.recovery_ready = False
            previous.recovery_id = None
            previous.segment_review_ready = False
            previous.segment_review_id = None
            previous.segment_review_index = None
            previous.updated_at = iso_now()
            self.db.finish_focus_session(previous)
        event = self._event("plan_cancelled", evidence)
        duration = float(self.cfg.get("duration_seconds", 1500.0))
        self.current = FocusState(
            state="IDLE", duration_seconds=duration, remaining_seconds=duration,
            last_action="学习计划已取消，可以创建新的学习计划",
        )
        self.face_missing_since = None
        self.face_returned_since = None
        self.phone_since = None
        self.phone_last_seen = None
        self.phone_episode_seconds = 0.0
        self.phone_latched = False
        self.gesture_latch = None
        self.last_checkpoint = now
        return {"ok": True, "event": event, "state": self.status()}

    def status(self) -> dict:
        value = self.current.to_dict()
        value["recovery"] = self._recovery_context()
        value["segment_review"] = self._segment_review_context()
        return value

    def checkpoint(self, now: float | None = None, force: bool = False) -> None:
        now = time.monotonic() if now is None else now
        interval = float(self.cfg.get("checkpoint_seconds", 5.0))
        if (self.current.session_id and self.current.state in {"RUNNING", "PAUSED", "AWAY"}
                and (force or now - self.last_checkpoint >= interval)):
            self.current.updated_at = iso_now()
            self.db.update_focus_session(self.current)
            self.last_checkpoint = now

    def _restore_latest_session(self) -> None:
        row = self.db.latest_resumable_focus_session()
        if not row:
            return
        try:
            plan = json.loads(row.get("plan_json") or "null")
        except (TypeError, ValueError, json.JSONDecodeError):
            plan = None
        try:
            skipped = [int(v) for v in json.loads(row.get("skipped_modules_json") or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            skipped = []
        try:
            segment_results = json.loads(row.get("segment_results_json") or "[]")
            if not isinstance(segment_results, list):
                segment_results = []
        except (TypeError, ValueError, json.JSONDecodeError):
            segment_results = []
        restored_state = str(row.get("state") or "PAUSED")
        self.current = FocusState(
            state=restored_state,
            session_id=row.get("session_id"),
            duration_seconds=float(row.get("duration_seconds") or 0.0),
            remaining_seconds=float(row.get("remaining_seconds") or 0.0),
            focused_seconds=float(row.get("focused_seconds") or 0.0),
            paused_seconds=float(row.get("paused_seconds") or 0.0),
            away_seconds=float(row.get("away_seconds") or 0.0),
            away_count=int(row.get("away_count") or 0),
            phone_reminders=int(row.get("phone_reminders") or 0),
            phone_usage_seconds=float(row.get("phone_usage_seconds") or 0.0),
            help_count=int(row.get("help_count") or 0),
            current_task=str(row.get("current_task") or ""),
            plan=plan if isinstance(plan, dict) else None,
            do_not_disturb=bool(row.get("do_not_disturb")),
            return_confirmation_required=bool(row.get("return_confirmation_required")),
            away_started_at=row.get("away_started_at"),
            current_away_seconds=float(row.get("current_away_seconds") or 0.0),
            recovery_ready=bool(row.get("recovery_ready")),
            recovery_id=row.get("recovery_id"),
            skipped_module_indices=skipped,
            segment_review_ready=bool(row.get("segment_review_ready")),
            segment_review_id=row.get("segment_review_id"),
            segment_review_index=row.get("segment_review_index"),
            segment_results=segment_results,
            last_action=str(row.get("last_action") or "专注会话已恢复"),
            updated_at=str(row.get("updated_at") or iso_now()),
        )
        if restored_state in {"RUNNING", "PAUSED"} and not self.current.segment_review_ready:
            self.current.state = "PAUSED"
            self.current.return_confirmation_required = True
            if not self.current.recovery_id:
                self.current.recovery_id = "recovery_" + uuid.uuid4().hex[:12]
                self.current.recovery_ready = True
                self.current.last_action = "服务已恢复，请选择继续当前模块或进入下一部分"
                self._record_recovery_prompt("service_restarted")
        self.db.update_focus_session(self.current)

    def _next_module_boundary(self, elapsed: float) -> dict | None:
        plan = self.current.plan if isinstance(self.current.plan, dict) else {}
        subtasks = plan.get("subtasks") if isinstance(plan.get("subtasks"), list) else []
        end = 0.0
        valid_indices = [i for i, item in enumerate(subtasks)
                         if isinstance(item, dict) and float(item.get("seconds") or 0) > 0]
        for index, subtask in enumerate(subtasks):
            if not isinstance(subtask, dict):
                continue
            try:
                seconds = max(0.0, float(subtask.get("seconds", 0.0)))
            except (TypeError, ValueError):
                seconds = 0.0
            if seconds <= 0:
                continue
            end += seconds
            if elapsed < end - 1e-6:
                return {
                    "index": index,
                    "label": str(subtask.get("label") or f"子任务{index + 1}"),
                    "seconds": seconds,
                    "end_seconds": end,
                    "is_final": index == valid_indices[-1],
                }
        return None

    def _prompt_segment_review(self, module: dict) -> dict:
        self.current.state = "PAUSED"
        self.current.segment_review_ready = True
        self.current.segment_review_id = "segment_" + uuid.uuid4().hex[:12]
        self.current.segment_review_index = int(module["index"])
        self.current.last_action = f"『{module['label']}』时间已到，请确认完成情况"
        context = self._segment_review_context()
        event = self._event("segment_completion_prompted", context)
        prompt = f"『{module['label']}』本段时间已到。是否已经完成？"
        if module.get("is_final"):
            prompt += "确认完成后将自动生成本次学习复盘报告。"
        else:
            prompt += "完成则进入下一段；未完成可补时后继续。"
        self.db.record_chat_message("assistant", prompt, "local-segment-review", self.current.session_id)
        self.db.update_focus_session(self.current)
        return event

    def _segment_review_context(self) -> dict:
        if not self.current.segment_review_ready or self.current.segment_review_index is None:
            return {"pending": False, "review_id": None, "module": None,
                    "is_final": False, "extension_seconds": int(self.cfg.get("segment_extension_seconds", 300))}
        plan = self.current.plan if isinstance(self.current.plan, dict) else {}
        subtasks = plan.get("subtasks") if isinstance(plan.get("subtasks"), list) else []
        index = int(self.current.segment_review_index)
        module = subtasks[index] if 0 <= index < len(subtasks) and isinstance(subtasks[index], dict) else {}
        valid = [i for i, item in enumerate(subtasks)
                 if isinstance(item, dict) and float(item.get("seconds") or 0) > 0]
        return {
            "pending": True,
            "review_id": self.current.segment_review_id,
            "module": {"index": index, "label": str(module.get("label") or f"子任务{index + 1}"),
                       "seconds": float(module.get("seconds") or 0)},
            "is_final": bool(valid and index == valid[-1]),
            "extension_seconds": int(self.cfg.get("segment_extension_seconds", 300)),
        }

    def _resolve_segment(self, completed: bool, payload: dict, now: float) -> dict:
        context = self._segment_review_context()
        if not context["pending"]:
            return {"ok": True, "ignored": True, "state": self.status()}
        module = context["module"]
        result = {
            "module_index": module["index"], "module_label": module["label"],
            "completed": completed, "answered_at": iso_now(),
            "source": str(payload.get("source") or "web"),
        }
        self.current.segment_results.append(result)
        self.current.segment_review_ready = False
        self.current.segment_review_id = None
        self.current.segment_review_index = None
        if completed:
            self.current.last_action = f"已确认完成『{module['label']}』"
            segment_event = self._event("segment_completed", result)
            self.db.record_chat_message("user", f"已完成：{module['label']}", result["source"], self.current.session_id)
            if context["is_final"]:
                final_event = self._finish("COMPLETED", "focus_completed")
                return {"ok": True, "event": final_event, "segment_event": segment_event,
                        "state": self.status(), "report": self.db.latest_focus_report()}
            self.current.state = "RUNNING"
            self.current.last_action += "，已进入下一段"
            event = segment_event
        else:
            extension = max(60, min(1800, int(context["extension_seconds"])))
            plan = self.current.plan if isinstance(self.current.plan, dict) else {}
            subtasks = plan.get("subtasks") if isinstance(plan.get("subtasks"), list) else []
            index = int(module["index"])
            if 0 <= index < len(subtasks) and isinstance(subtasks[index], dict):
                subtasks[index]["seconds"] = float(subtasks[index].get("seconds") or 0) + extension
                plan["total_seconds"] = float(plan.get("total_seconds") or self.current.duration_seconds) + extension
            self.current.duration_seconds += extension
            self.current.remaining_seconds += extension
            result["extension_seconds"] = extension
            self.current.state = "RUNNING"
            self.current.last_action = f"『{module['label']}』未完成，已补时 {extension // 60} 分钟"
            event = self._event("segment_extended", result)
            self.db.record_chat_message("user", f"未完成：{module['label']}，补时{extension // 60}分钟",
                                        result["source"], self.current.session_id)
        self.db.record_chat_message("assistant", self.current.last_action, "local-segment-review", self.current.session_id)
        self.current.updated_at = iso_now()
        self.db.update_focus_session(self.current)
        self.last_checkpoint = now
        return {"ok": True, "event": event, "state": self.status()}

    def _enter_away(self) -> dict:
        self.current.state = "AWAY"
        self.current.away_count += 1
        self.current.return_confirmation_required = True
        self.current.away_started_at = iso_now()
        self.current.current_away_seconds = 0.0
        self.current.recovery_ready = False
        self.current.recovery_id = None
        self.current.last_action = "用户离席，专注计时已暂停"
        self.face_returned_since = None
        event = self._event("away", self._recovery_context())
        self.db.update_focus_session(self.current)
        return event

    def _prepare_recovery(self, reason: str) -> dict:
        self.current.recovery_ready = True
        self.current.recovery_id = self.current.recovery_id or "recovery_" + uuid.uuid4().hex[:12]
        self.current.last_action = "已检测到返回，请选择继续当前模块或进入下一部分"
        return self._record_recovery_prompt(reason)

    def _record_recovery_prompt(self, reason: str) -> dict:
        context = self._recovery_context()
        event = self._event("recovery_prompted", {"reason": reason, **context})
        current_label = (context.get("current_module") or {}).get("label") or "当前模块"
        next_label = (context.get("next_module") or {}).get("label")
        prompt = f"欢迎回来。继续『{current_label}』"
        prompt += f"，还是进入『{next_label}』？" if next_label else "？当前已经是计划的最后一部分。"
        if context.get("show_summary"):
            prompt += "\n" + str(context.get("summary_text") or "")
        self.db.record_chat_message("assistant", prompt, "local-recovery", self.current.session_id)
        self.db.update_focus_session(self.current)
        return event

    def _resolve_recovery(self, action: str, payload: dict, now: float) -> dict:
        if not self.current.return_confirmation_required:
            return {"ok": True, "ignored": True, "state": self.status()}
        if not self.current.recovery_ready:
            return {"ok": True, "ignored": True, "reason": "等待稳定检测到用户返回", "state": self.status()}
        if action not in {"continue", "next"}:
            raise ValueError("恢复操作必须是continue或next")

        context = self._recovery_context()
        current_module = context.get("current_module") or {}
        next_module = context.get("next_module")
        evidence = {
            "recovery_id": self.current.recovery_id,
            "away_seconds": round(self.current.current_away_seconds, 1),
            "current_module": current_module,
            "source": str(payload.get("source") or "web"),
        }
        if action == "next":
            if not next_module:
                raise ValueError("当前已经是计划的最后一部分")
            current_index = int(current_module["index"])
            if current_index not in self.current.skipped_module_indices:
                self.current.skipped_module_indices.append(current_index)
                self.current.skipped_module_indices.sort()
            self.current.remaining_seconds = max(
                0.0, self.current.duration_seconds - float(next_module["start_seconds"])
            )
            self.current.last_action = f"已跳过『{current_module['label']}』，进入『{next_module['label']}』"
            evidence["skipped_remaining_seconds"] = current_module.get("remaining_seconds", 0.0)
            evidence["next_module"] = next_module
            event_type = "recovery_next_module"
            user_message = f"进入下一部分：{next_module['label']}"
        else:
            self.current.last_action = f"已继续『{current_module.get('label') or self.current.current_task or '当前任务'}』"
            event_type = "recovery_continued"
            user_message = f"继续当前模块：{current_module.get('label') or self.current.current_task or '当前任务'}"

        self.current.state = "RUNNING"
        self.current.return_confirmation_required = False
        self.current.recovery_ready = False
        self.current.recovery_id = None
        self.current.away_started_at = None
        self.current.current_away_seconds = 0.0
        self.face_missing_since = None
        self.face_returned_since = None
        self.current.updated_at = iso_now()
        event = self._event(event_type, evidence)
        self.db.record_chat_message("user", user_message, str(payload.get("source") or "web"), self.current.session_id)
        self.db.record_chat_message("assistant", self.current.last_action, "local-recovery", self.current.session_id)
        self.db.update_focus_session(self.current)
        self.last_checkpoint = now
        return {"ok": True, "event": event, "state": self.status()}

    def _plan_position(self) -> tuple[dict | None, dict | None]:
        plan = self.current.plan if isinstance(self.current.plan, dict) else {}
        subtasks = plan.get("subtasks") if isinstance(plan.get("subtasks"), list) else []
        elapsed = max(0.0, self.current.duration_seconds - self.current.remaining_seconds)
        start = 0.0
        current = None
        current_index = -1
        for index, subtask in enumerate(subtasks):
            if not isinstance(subtask, dict):
                continue
            try:
                seconds = max(0.0, float(subtask.get("seconds", 0.0)))
            except (TypeError, ValueError):
                seconds = 0.0
            end = start + seconds
            if seconds > 0.0 and elapsed < end:
                within = max(0.0, elapsed - start)
                current = {
                    "index": index,
                    "label": str(subtask.get("label") or f"子任务{index + 1}"),
                    "seconds": seconds,
                    "start_seconds": start,
                    "remaining_seconds": max(0.0, seconds - within),
                    "progress_percent": round(min(1.0, within / seconds) * 100.0, 1),
                }
                current_index = index
                break
            start = end
        next_module = None
        if current is not None:
            next_start = current["start_seconds"] + current["seconds"]
            for index in range(current_index + 1, len(subtasks)):
                subtask = subtasks[index]
                if not isinstance(subtask, dict):
                    continue
                try:
                    seconds = max(0.0, float(subtask.get("seconds", 0.0)))
                except (TypeError, ValueError):
                    seconds = 0.0
                if seconds > 0.0:
                    next_module = {
                        "index": index,
                        "label": str(subtask.get("label") or f"子任务{index + 1}"),
                        "seconds": seconds,
                        "start_seconds": next_start,
                    }
                    break
                next_start += seconds
        return current, next_module

    def _recovery_context(self) -> dict:
        current, next_module = self._plan_position()
        pending = bool(self.current.return_confirmation_required and self.current.recovery_ready)
        threshold = float(self.cfg.get("recovery_summary_seconds", 300.0))
        show_summary = self.current.current_away_seconds >= threshold
        summary_text = ""
        if show_summary:
            label = (current or {}).get("label") or self.current.current_task or "当前任务"
            progress = (current or {}).get("progress_percent", 0.0)
            remaining = (current or {}).get("remaining_seconds", self.current.remaining_seconds)
            summary_text = (
                f"任务：{self.current.current_task or '未命名任务'}；当前模块：{label}；"
                f"已完成 {progress:.0f}%；剩余 {remaining / 60.0:.1f} 分钟；"
                f"本次离席 {self.current.current_away_seconds / 60.0:.1f} 分钟。"
            )
        return {
            "pending": pending,
            "recovery_id": self.current.recovery_id,
            "away_seconds": round(self.current.current_away_seconds, 1),
            "current_module": current,
            "next_module": next_module,
            "show_summary": show_summary,
            "summary_text": summary_text,
        }

    def _restart_plan_module(self) -> dict | None:
        """Restart the saved plan at the beginning of its current module."""
        previous = self.current
        plan = previous.plan if isinstance(previous.plan, dict) else None
        subtasks = plan.get("subtasks") if plan else None
        if not isinstance(subtasks, list) or not subtasks:
            return None

        elapsed = max(0.0, previous.duration_seconds - previous.remaining_seconds)
        module = None
        start = 0.0
        for index, subtask in enumerate(subtasks):
            try:
                seconds = max(0.0, float(subtask.get("seconds", 0.0)))
            except (AttributeError, TypeError, ValueError):
                seconds = 0.0
            end = start + seconds
            if seconds > 0.0 and elapsed < end:
                module = (index, str(subtask.get("label") or f"子任务{index + 1}"), start, seconds)
                break
            start = end
        if module is None:
            return None

        index, label, module_start, module_seconds = module
        duration = previous.duration_seconds
        self.current = FocusState(
            state="RUNNING",
            session_id="focus_" + uuid.uuid4().hex[:12],
            duration_seconds=duration,
            remaining_seconds=max(0.0, duration - module_start),
            current_task=previous.current_task,
            plan=plan,
            do_not_disturb=previous.do_not_disturb,
            last_action=f"已按计划时长重新开始：{label}",
        )
        self.db.start_focus_session(self.current)
        return self._event("focus_module_restarted", {
            "module_index": index,
            "module_label": label,
            "module_seconds": module_seconds,
            "remaining_seconds": self.current.remaining_seconds,
        })

    def _transition(self, state: str, event_type: str, action: str) -> dict:
        self.current.state = state
        self.current.last_action = action
        event = self._event(event_type, {})
        if self.current.session_id:
            self.db.update_focus_session(self.current)
        return event

    def _finish(self, state: str, event_type: str) -> dict:
        self.current.state = state
        self.current.segment_review_ready = False
        self.current.segment_review_id = None
        self.current.segment_review_index = None
        self.current.return_confirmation_required = False
        self.current.recovery_ready = False
        self.current.recovery_id = None
        self.current.last_action = "专注会话已完成" if state == "COMPLETED" else "专注会话已停止并保存"
        self.db.finish_focus_session(self.current)
        report = self._generate_report(state)
        event = self._event(event_type, self.summary() | {"report_session_id": self.current.session_id})
        return event

    def _generate_report(self, state: str) -> dict:
        metrics = self.summary() | {
            "duration_seconds": round(self.current.duration_seconds, 1),
            "segment_results": self.current.segment_results,
            "skipped_module_indices": self.current.skipped_module_indices,
        }
        active = self.current.focused_seconds + self.current.paused_seconds + self.current.away_seconds
        focus_rate = self.current.focused_seconds / active * 100.0 if active > 0 else 0.0
        plan = self.current.plan if isinstance(self.current.plan, dict) else {}
        subtasks = plan.get("subtasks") if isinstance(plan.get("subtasks"), list) else []
        latest_results = {int(item.get("module_index", -1)): item for item in self.current.segment_results}
        module_lines = []
        for index, item in enumerate(subtasks):
            if not isinstance(item, dict):
                continue
            answer = latest_results.get(index)
            status = "已完成" if answer and answer.get("completed") else ("未完成并补时" if answer else "未确认")
            if index in self.current.skipped_module_indices:
                status = "已跳过"
            module_lines.append(f"- {item.get('label') or f'子任务{index + 1}'}：{status}")
        suggestions = []
        if self.current.phone_reminders:
            suggestions.append(
                f"本次识别到 {self.current.phone_reminders} 次手机使用、累计"
                f" {self._format_duration(self.current.phone_usage_seconds)}，"
                "下次可提前开启免打扰并将手机移出桌面。"
            )
        if self.current.away_count:
            suggestions.append(f"本次离席 {self.current.away_count} 次、累计 {self.current.away_seconds / 60.0:.1f} 分钟，建议在下一学习段前准备好资料和饮水。")
        if focus_rate < 70:
            suggestions.append("有效专注占比较低，下一次可缩短单段时长，并在段间安排固定休息。")
        if not suggestions:
            suggestions.append("本次过程较稳定，建议保持当前节奏，并在下一次复习开始前快速回顾本次总结。")
        outcome = "按计划完成" if state == "COMPLETED" else "提前结束并已保存"
        content = "\n".join([
            f"## {self.current.current_task or '专注学习'} · 自动复盘报告",
            "",
            f"- 结果：{outcome}",
            f"- 有效专注：{self.current.focused_seconds / 60.0:.1f} 分钟",
            f"- 暂停：{self.current.paused_seconds / 60.0:.1f} 分钟",
            f"- 离席：{self.current.away_seconds / 60.0:.1f} 分钟（{self.current.away_count} 次）",
            f"- 手机使用：{self.current.phone_reminders} 次（累计 {self._format_duration(self.current.phone_usage_seconds)}）",
            f"- 有效专注占比：{focus_rate:.0f}%",
            "", "### 分段完成情况", *(module_lines or ["- 本次为普通计时，未设置分段计划。"]),
            "", "### Agent 建议", *[f"- {item}" for item in suggestions],
        ])
        report = self.db.save_focus_report(
            self.current.session_id or "", self.current.current_task or "专注学习",
            state, content, metrics,
        )
        self.db.save_report(content, "local-agent")
        self.db.record_chat_message("assistant", content, "local-report", self.current.session_id)
        return report

    def _event(self, event_type: str, evidence: dict) -> dict:
        event = {
            "event_id": "int_" + uuid.uuid4().hex[:12],
            "session_id": self.current.session_id,
            "type": event_type,
            "created_at": iso_now(),
            "evidence": evidence,
        }
        self.db.record_interaction(event)
        return event

    def summary(self) -> dict:
        return {
            "focused_seconds": round(self.current.focused_seconds, 1),
            "paused_seconds": round(self.current.paused_seconds, 1),
            "away_seconds": round(self.current.away_seconds, 1),
            "away_count": self.current.away_count,
            "phone_reminders": self.current.phone_reminders,
            "phone_usage_count": self.current.phone_reminders,
            "phone_usage_seconds": round(self.current.phone_usage_seconds, 1),
            "help_count": self.current.help_count,
            "current_task": self.current.current_task,
        }

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        minutes, remainder = divmod(seconds, 60)
        if not minutes:
            return f"{remainder} 秒"
        if not remainder:
            return f"{minutes} 分钟"
        return f"{minutes} 分 {remainder} 秒"

    @staticmethod
    def _gesture_command(name: str) -> str:
        return {
            "OK": "resume_focus",
            "OPEN_PALM": "pause_focus",
            "FIST": "stop_focus",
            "THUMB_DOWN": "toggle_do_not_disturb",
            "VICTORY": "open_help",
        }.get(name, "")
