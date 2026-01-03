import os
import sqlite3
import statistics
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, render_template,
    redirect, url_for, session, flash,
    send_file, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from pydantic import ValidationError

# =============================
# IMPORT EXISTING MODULES
# =============================
from config import KB_DIR, UPLOAD_DIR
from db import init_db as init_logs_db, log_interaction, recent_logs
from rag import ingest_text
from agents import tutor_chat, generate_lesson_plan, rubric_feedback
from schemas import ChatRequest, LessonRequest, FeedbackRequest

# =============================
# FLASK INITIALIZATION
# =============================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

USER_DB = "users.db"
SURVEY_DB = "survey.db"
EXPORT_CSV = "survey_dataset.csv"

os.makedirs(KB_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
init_logs_db()

# =============================
# DATABASE HELPERS
# =============================
def user_db():
    conn = sqlite3.connect(USER_DB)
    conn.row_factory = sqlite3.Row
    return conn

def survey_db():
    try:
        conn = sqlite3.connect(SURVEY_DB)
        conn.execute("SELECT 1")
        return conn
    except sqlite3.DatabaseError:
        try:
            if os.path.exists(SURVEY_DB):
                os.remove(SURVEY_DB)
        except Exception:
            pass
        return sqlite3.connect(SURVEY_DB)

# =============================
# INIT DATABASES
# =============================
def init_users_db():
    conn = user_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','lecturer','student')),
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, 'admin', ?)
        """, ("admin", generate_password_hash("admin123"), datetime.utcnow().isoformat()))
        conn.commit()

    conn.close()

def init_survey_db():
    conn = survey_db()
    cur = conn.cursor()

    cols = ",\n".join([f"R{i} INTEGER CHECK(R{i} BETWEEN 1 AND 5)" for i in range(1, 41)])

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS likert_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {cols},
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# =============================
# AUTH HELPERS
# =============================
def get_user(username):
    conn = user_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    u = cur.fetchone()
    conn.close()
    return u

def get_user_by_id(uid):
    conn = user_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    u = cur.fetchone()
    conn.close()
    return u

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# =============================
# AUTH ROUTES
# =============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_user(request.form.get("username", "").strip())
        if not user or not check_password_hash(user["password_hash"], request.form.get("password", "")):
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))

        session.update({
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"]
        })
        return redirect(url_for("home"))

    return render_template("user_login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/")
@login_required
def home():
    return render_template("index.html", username=session["username"], role=session["role"])

# =============================
# API ROUTES
# =============================
@app.post("/api/chat")
@login_required
def api_chat():
    try:
        req = ChatRequest(**(request.get_json() or {}))
        out = tutor_chat(req.message)
        log_interaction(session["role"], "chat", req.message, out, 0)
        return jsonify({"reply": out})
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/lesson")
@login_required
@role_required("admin", "lecturer")
def api_lesson():
    try:
        req = LessonRequest(**(request.get_json() or {}))
        out = generate_lesson_plan(req.topic, req.level, req.subject, req.duration_min)
        return jsonify({"reply": out})
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/feedback")
@login_required
@role_required("admin", "lecturer")
def api_feedback():
    try:
        req = FeedbackRequest(**(request.get_json() or {}))
        out = rubric_feedback(req.lesson_text, req.rubric_text)
        return jsonify({"reply": out})
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =============================
# SURVEY ROUTES
# =============================
@app.post("/api/survey/submit")
@login_required
def submit_survey():
    try:
        data = request.get_json() or {}
        role = data.get("role", session["role"])
        values = [int(data[f"R{i}"]) for i in range(1, 41)]

        conn = survey_db()
        cur = conn.cursor()
        cols = ", ".join([f"R{i}" for i in range(1, 41)])
        cur.execute(
            f"INSERT INTO likert_responses ({cols}, role, created_at) VALUES ({','.join(['?']*40)}, ?, ?)",
            (*values, role, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/survey/responses")
@login_required
@role_required("admin")
def survey_responses():
    conn = survey_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM likert_responses ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

# =============================
# ENTRY POINT (RENDER SAFE)
# =============================
init_users_db()
init_survey_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
