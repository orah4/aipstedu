import os
import sqlite3
from datetime import datetime
from config import SQLITE_PATH, STORAGE_DIR

def _connect():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    return sqlite3.connect(SQLITE_PATH)

def init_db():
    con = _connect()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        role TEXT NOT NULL,
        action TEXT NOT NULL,
        input TEXT NOT NULL,
        output TEXT NOT NULL,
        approved INTEGER NOT NULL DEFAULT 0,
        reviewer TEXT DEFAULT ''
    );
    """)
    con.commit()
    con.close()

def log_interaction(role: str, action: str, user_input: str, output: str, approved: int = 0, reviewer: str = ""):
    con = _connect()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO interactions (ts, role, action, input, output, approved, reviewer)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (datetime.utcnow().isoformat(), role, action, user_input, output, approved, reviewer))
    con.commit()
    con.close()

def approve_interaction(interaction_id: int, reviewer: str):
    con = _connect()
    cur = con.cursor()
    cur.execute("""
        UPDATE interactions SET approved=1, reviewer=? WHERE id=?
    """, (reviewer, interaction_id))
    con.commit()
    con.close()

def recent_logs(limit: int = 20):
    con = _connect()
    cur = con.cursor()
    cur.execute("""
        SELECT id, ts, role, action, approved, reviewer, substr(input,1,120), substr(output,1,120)
        FROM interactions ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    con.close()
    return rows
