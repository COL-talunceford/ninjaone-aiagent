import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Optional
from config import settings

DB_PATH = settings.AGENT_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket_solution (
  ticket_id INTEGER PRIMARY KEY,
  solution_json TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
    finally:
        con.close()

def init_db():
    with _conn() as c:
        c.execute(SCHEMA)
        c.commit()

def save_solution(ticket_id: int, solution: Dict[str, Any]) -> None:
    data = json.dumps(solution, ensure_ascii=False)
    with _conn() as c:
        c.execute(
            "INSERT INTO ticket_solution(ticket_id, solution_json) VALUES(?, ?) "
            "ON CONFLICT(ticket_id) DO UPDATE SET solution_json=excluded.solution_json, created_at=CURRENT_TIMESTAMP",
            (ticket_id, data),
        )
        c.commit()

def get_solution(ticket_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        cur = c.execute("SELECT solution_json FROM ticket_solution WHERE ticket_id=?", (ticket_id,))
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

