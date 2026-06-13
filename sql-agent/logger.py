"""
logger.py — Correction-chain logger with persistence (#8).
Saves every session to SQLite so history survives page refreshes.
"""
import json
import os
import time
import sqlite3
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime


@dataclass
class AttemptRecord:
    attempt_number: int
    sql: str
    success: bool
    error: Optional[str]
    execution_time_ms: float
    row_count: int
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class QuerySession:
    session_id: str
    question: str
    model: str
    total_attempts: int = 0
    final_success: bool = False
    final_row_count: int = 0
    explanation: str = ""
    attempts: List[AttemptRecord] = field(default_factory=list)
    start_time: float = field(default_factory=time.perf_counter)
    total_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def add_attempt(self, record: AttemptRecord):
        self.attempts.append(record)
        self.total_attempts += 1

    def finalize(self, success: bool, row_count: int = 0, explanation: str = ""):
        self.final_success  = success
        self.final_row_count= row_count
        self.explanation    = explanation
        self.total_time_ms  = round(
            (time.perf_counter() - self.start_time) * 1000, 2
        )


# ── Persistent SQLite-backed logger (#8) ─────────────────────────────────────
HISTORY_DB = os.path.join(os.path.dirname(__file__), "logs", "history.db")


class CorrectionLogger:
    """In-memory + SQLite-persisted correction chain logger."""

    def __init__(self, log_dir: Optional[str] = None):
        self.sessions: List[QuerySession] = []
        self.log_dir = log_dir or os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self._db_path = os.path.join(self.log_dir, "history.db")
        self._init_db()
        self._load_from_db()          # restore history on startup

    # ── DB setup ─────────────────────────────────────────────────────────────
    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                question     TEXT,
                model        TEXT,
                total_attempts INTEGER,
                final_success  INTEGER,
                final_row_count INTEGER,
                total_time_ms REAL,
                explanation  TEXT,
                timestamp    TEXT,
                attempts_json TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _save_session(self, s: QuerySession):
        conn = sqlite3.connect(self._db_path)
        attempts_json = json.dumps([asdict(a) for a in s.attempts])
        conn.execute("""
            INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            s.session_id, s.question, s.model, s.total_attempts,
            int(s.final_success), s.final_row_count, s.total_time_ms,
            s.explanation, s.timestamp, attempts_json
        ))
        conn.commit()
        conn.close()

    def _load_from_db(self, limit: int = 100):
        """Load the last `limit` sessions from disk into memory."""
        try:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            loaded = []
            for row in reversed(rows):
                (sid, q, m, n_att, ok, n_rows, t_ms, expl, ts, att_json) = row
                attempts = [
                    AttemptRecord(**a)
                    for a in json.loads(att_json or "[]")
                ]
                sess = QuerySession(
                    session_id=sid, question=q, model=m,
                    total_attempts=n_att,
                    final_success=bool(ok),
                    final_row_count=n_rows,
                    total_time_ms=t_ms,
                    explanation=expl or "",
                    attempts=attempts,
                    timestamp=ts,
                )
                loaded.append(sess)
            self.sessions = loaded
        except Exception:
            self.sessions = []

    # ── Public API ────────────────────────────────────────────────────────────
    def new_session(self, question: str, model: str) -> QuerySession:
        session_id = f"sess_{int(time.time() * 1000)}"
        session    = QuerySession(session_id=session_id, question=question, model=model)
        self.sessions.append(session)
        return session

    def log_attempt(
        self,
        session: QuerySession,
        attempt_number: int,
        sql: str,
        success: bool,
        error: Optional[str],
        execution_time_ms: float,
        row_count: int = 0,
    ):
        record = AttemptRecord(
            attempt_number=attempt_number, sql=sql, success=success,
            error=error, execution_time_ms=execution_time_ms, row_count=row_count,
        )
        session.add_attempt(record)
        return record

    def finalize_session(
        self, session: QuerySession,
        success: bool, row_count: int = 0, explanation: str = ""
    ):
        session.finalize(success, row_count, explanation)
        self._save_session(session)         # persist to disk (#8)

    def get_stats(self) -> dict:
        if not self.sessions:
            return {}
        total     = len(self.sessions)
        succeeded = sum(1 for s in self.sessions if s.final_success)
        first_try = sum(1 for s in self.sessions if s.final_success and s.total_attempts == 1)
        avg_att   = sum(s.total_attempts for s in self.sessions) / total
        avg_time  = sum(s.total_time_ms  for s in self.sessions) / total
        return {
            "total_queries": total,
            "success_rate":  round(succeeded / total * 100, 1),
            "first_try_rate":round(first_try  / total * 100, 1),
            "avg_attempts":  round(avg_att, 2),
            "avg_time_ms":   round(avg_time, 1),
        }

    def get_recent_sessions(self, n: int = 10) -> List[QuerySession]:
        return self.sessions[-n:]

    def search_history(self, keyword: str) -> List[QuerySession]:
        """Search sessions by keyword in question text (#8)."""
        kw = keyword.lower()
        return [s for s in self.sessions if kw in s.question.lower()]

    def clear(self):
        self.sessions.clear()
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM sessions")
            conn.commit()
            conn.close()
        except Exception:
            pass
