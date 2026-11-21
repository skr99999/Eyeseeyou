from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading

from .models import AgentEvent, FatigueState, iso_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fatigue_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  started_at TEXT NOT NULL,
  duration_seconds REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  action TEXT NOT NULL,
  acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS agent_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  input_json TEXT NOT NULL,
  decision TEXT NOT NULL,
  tool TEXT,
  result_json TEXT
);
CREATE TABLE IF NOT EXISTS alarms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  event_id TEXT,
  played INTEGER NOT NULL,
  muted INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS acknowledgements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  event_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  state TEXT NOT NULL,
  risk_score REAL NOT NULL,
  ear REAL,
  mar REAL,
  perclos REAL NOT NULL,
  pitch REAL,
  blinks INTEGER NOT NULL,
  yawns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_reports (
  report_date TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS focus_reports (
  session_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  task TEXT NOT NULL,
  completion_state TEXT NOT NULL,
  source TEXT NOT NULL,
  content TEXT NOT NULL,
  metrics_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS focus_sessions (
  session_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  state TEXT NOT NULL,
  duration_seconds REAL NOT NULL,
  remaining_seconds REAL NOT NULL,
  focused_seconds REAL NOT NULL DEFAULT 0,
  paused_seconds REAL NOT NULL DEFAULT 0,
  away_seconds REAL NOT NULL DEFAULT 0,
  away_count INTEGER NOT NULL DEFAULT 0,
  phone_reminders INTEGER NOT NULL DEFAULT 0,
  phone_usage_seconds REAL NOT NULL DEFAULT 0,
  help_count INTEGER NOT NULL DEFAULT 0,
  do_not_disturb INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS interaction_events (
  event_id TEXT PRIMARY KEY,
  session_id TEXT,
  event_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  evidence_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  session_id TEXT,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  source TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.conn:
            self.conn.executescript(SCHEMA)
            self._ensure_column("focus_sessions", "current_task", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("focus_sessions", "plan_json", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("focus_sessions", "return_confirmation_required", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("focus_sessions", "away_started_at", "TEXT")
            self._ensure_column("focus_sessions", "current_away_seconds", "REAL NOT NULL DEFAULT 0")
            self._ensure_column("focus_sessions", "recovery_ready", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("focus_sessions", "recovery_id", "TEXT")
            self._ensure_column("focus_sessions", "skipped_modules_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column("focus_sessions", "last_action", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("focus_sessions", "updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("focus_sessions", "segment_review_ready", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("focus_sessions", "segment_review_id", "TEXT")
            self._ensure_column("focus_sessions", "segment_review_index", "INTEGER")
            self._ensure_column("focus_sessions", "segment_results_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column("focus_sessions", "phone_usage_seconds", "REAL NOT NULL DEFAULT 0")

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        existing = {
            str(row["name"]) for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def record_event(self, event: AgentEvent) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO fatigue_events VALUES(?,?,?,?,?,?,?,?)",
                (event.event_id, event.type, event.severity, event.started_at,
                 event.duration_seconds, json.dumps(event.evidence, ensure_ascii=False),
                 event.action, int(event.acknowledged)),
            )

    def recent_events(self, limit: int = 50) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM fatigue_events ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) | {"evidence": json.loads(row["evidence_json"])} for row in rows]

    def acknowledge(self, event_id: str) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "UPDATE fatigue_events SET acknowledged=1 WHERE event_id=?", (event_id,)
            )
            if cur.rowcount:
                self.conn.execute(
                    "INSERT INTO acknowledgements(created_at,event_id) VALUES(?,?)",
                    (iso_now(), event_id),
                )
            return bool(cur.rowcount)

    def record_state(self, state: FatigueState) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                """INSERT INTO observations_summary(
                created_at,state,risk_score,ear,mar,perclos,pitch,blinks,yawns)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (state.updated_at, state.state, state.risk_score, state.ear, state.mar,
                 state.perclos, state.pitch, state.blinks_total, state.yawn_count),
            )

    def record_alarm(self, event_id: str | None, played: bool, muted: bool) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO alarms(created_at,event_id,played,muted) VALUES(?,?,?,?)",
                (iso_now(), event_id, int(played), int(muted)),
            )

    def record_decision(self, state: dict, decision: str, tool: str | None, result: dict) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO agent_decisions(created_at,input_json,decision,tool,result_json) VALUES(?,?,?,?,?)",
                (iso_now(), json.dumps(state, ensure_ascii=False), decision, tool,
                 json.dumps(result, ensure_ascii=False)),
            )

    def today_statistics(self) -> dict:
        today = iso_now()[:10]
        with self.lock:
            summary = self.conn.execute(
                """SELECT COUNT(*) samples, MAX(risk_score) max_risk,
                AVG(perclos) avg_perclos, MAX(blinks) blinks, MAX(yawns) yawns
                FROM observations_summary WHERE created_at LIKE ?""", (today + "%",)
            ).fetchone()
            events = self.conn.execute(
                "SELECT severity,COUNT(*) count FROM fatigue_events WHERE started_at LIKE ? GROUP BY severity",
                (today + "%",),
            ).fetchall()
        return {
            "date": today,
            "samples": int(summary["samples"] or 0),
            "max_risk": float(summary["max_risk"] or 0.0),
            "avg_perclos": float(summary["avg_perclos"] or 0.0),
            "blinks": int(summary["blinks"] or 0),
            "yawns": int(summary["yawns"] or 0),
            "events": {row["severity"]: row["count"] for row in events},
        }

    def save_report(self, content: str, source: str) -> None:
        today = iso_now()[:10]
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO daily_reports VALUES(?,?,?,?)",
                (today, iso_now(), source, content),
            )

    def save_focus_report(self, session_id: str, task: str, completion_state: str,
                          content: str, metrics: dict, source: str = "local-agent") -> dict:
        report = {
            "session_id": session_id,
            "created_at": iso_now(),
            "task": task,
            "completion_state": completion_state,
            "source": source,
            "content": content,
            "metrics": metrics,
        }
        with self.lock, self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO focus_reports(
                session_id,created_at,task,completion_state,source,content,metrics_json)
                VALUES(?,?,?,?,?,?,?)""",
                (session_id, report["created_at"], task, completion_state, source, content,
                 json.dumps(metrics, ensure_ascii=False)),
            )
        return report

    def latest_focus_report(self) -> dict | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM focus_reports ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["metrics"] = json.loads(value.pop("metrics_json") or "{}")
        return value

    def start_focus_session(self, state) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO focus_sessions(
                session_id,started_at,state,duration_seconds,remaining_seconds,
                focused_seconds,paused_seconds,away_seconds,away_count,
                phone_reminders,phone_usage_seconds,help_count,do_not_disturb,current_task,plan_json,
                return_confirmation_required,away_started_at,current_away_seconds,
                recovery_ready,recovery_id,skipped_modules_json,last_action,updated_at,
                segment_review_ready,segment_review_id,segment_review_index,segment_results_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (state.session_id, iso_now(), state.state, state.duration_seconds,
                 state.remaining_seconds, state.focused_seconds, state.paused_seconds,
                 state.away_seconds, state.away_count, state.phone_reminders,
                 state.phone_usage_seconds, state.help_count, int(state.do_not_disturb), state.current_task,
                 json.dumps(state.plan, ensure_ascii=False) if state.plan else "",
                 int(state.return_confirmation_required), state.away_started_at,
                 state.current_away_seconds, int(state.recovery_ready), state.recovery_id,
                 json.dumps(state.skipped_module_indices), state.last_action, state.updated_at,
                 int(state.segment_review_ready), state.segment_review_id,
                 state.segment_review_index,
                 json.dumps(state.segment_results, ensure_ascii=False)),
            )

    def update_focus_session(self, state) -> None:
        if not state.session_id:
            return
        with self.lock, self.conn:
            self.conn.execute(
                """UPDATE focus_sessions SET state=?,remaining_seconds=?,focused_seconds=?,
                paused_seconds=?,away_seconds=?,away_count=?,phone_reminders=?,phone_usage_seconds=?,help_count=?,
                do_not_disturb=?,current_task=?,plan_json=?,return_confirmation_required=?,
                away_started_at=?,current_away_seconds=?,recovery_ready=?,recovery_id=?,
                skipped_modules_json=?,last_action=?,updated_at=?,segment_review_ready=?,
                segment_review_id=?,segment_review_index=?,segment_results_json=?
                WHERE session_id=?""",
                (state.state, state.remaining_seconds, state.focused_seconds,
                 state.paused_seconds, state.away_seconds, state.away_count,
                 state.phone_reminders, state.phone_usage_seconds, state.help_count,
                 int(state.do_not_disturb), state.current_task,
                 json.dumps(state.plan, ensure_ascii=False) if state.plan else "",
                 int(state.return_confirmation_required), state.away_started_at,
                 state.current_away_seconds, int(state.recovery_ready), state.recovery_id,
                 json.dumps(state.skipped_module_indices), state.last_action, state.updated_at,
                 int(state.segment_review_ready), state.segment_review_id,
                 state.segment_review_index,
                 json.dumps(state.segment_results, ensure_ascii=False),
                 state.session_id),
            )

    def finish_focus_session(self, state) -> None:
        self.update_focus_session(state)
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE focus_sessions SET ended_at=? WHERE session_id=?",
                (iso_now(), state.session_id),
            )

    def record_interaction(self, event: dict) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO interaction_events VALUES(?,?,?,?,?)",
                (event["event_id"], event.get("session_id"), event["type"],
                 event["created_at"], json.dumps(event.get("evidence", {}), ensure_ascii=False)),
            )

    def recent_interactions(self, limit: int = 100) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM interaction_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) | {"evidence": json.loads(row["evidence_json"])} for row in rows]

    def latest_focus_session(self) -> dict | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM focus_sessions ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return None if row is None else dict(row)

    def latest_resumable_focus_session(self) -> dict | None:
        with self.lock:
            row = self.conn.execute(
                """SELECT * FROM focus_sessions
                WHERE ended_at IS NULL AND state IN ('RUNNING','PAUSED','AWAY')
                ORDER BY started_at DESC LIMIT 1"""
            ).fetchone()
        return None if row is None else dict(row)

    def record_chat_message(self, role: str, content: str, source: str,
                            session_id: str | None = None) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("聊天角色必须是user或assistant")
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO chat_messages(created_at,session_id,role,content,source) VALUES(?,?,?,?,?)",
                (iso_now(), session_id, role, content, source),
            )

    def recent_chat_messages(self, limit: int = 20) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                """SELECT id,created_at,session_id,role,content,source FROM (
                SELECT * FROM chat_messages ORDER BY id DESC LIMIT ?)
                ORDER BY id ASC""", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self.lock:
            self.conn.close()
