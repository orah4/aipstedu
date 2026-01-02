import os
import sqlite3
import statistics
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, render_template,
    redirect, url_for, session, flash, send_file
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
app.secret_key = "CHANGE_THIS_TO_A_RANDOM_SECRET_KEY"

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
    """
    Returns a valid survey DB connection.
    If survey.db exists but is corrupted (not a database),
    recreate it safely.
    """
    try:
        conn = sqlite3.connect(SURVEY_DB)
        # quick integrity probe
        conn.execute("SELECT 1")
        return conn
    except sqlite3.DatabaseError:
        # corrupted file: remove and recreate
        try:
            if os.path.exists(SURVEY_DB):
                os.remove(SURVEY_DB)
        except Exception:
            pass
        conn = sqlite3.connect(SURVEY_DB)
        return conn

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

    # Seed default admin
    cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, 'admin', ?)
        """, (
            "admin",
            generate_password_hash("admin123"),
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        print("✅ Default admin created (admin / admin123)")

    conn.close()


# def init_survey_db():
#     conn = survey_db()
#     cur = conn.cursor()

#     cur.execute("""
#         CREATE TABLE IF NOT EXISTS likert_responses (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             respondent TEXT NOT NULL,
#             question TEXT NOT NULL,
#             score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
#             role TEXT NOT NULL,
#             created_at TEXT NOT NULL
#         )
#     """)

#     conn.commit()
#     conn.close()


def init_survey_db():
    conn = survey_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS likert_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            R1  INTEGER CHECK(R1 BETWEEN 1 AND 5),
            R2  INTEGER CHECK(R2 BETWEEN 1 AND 5),
            R3  INTEGER CHECK(R3 BETWEEN 1 AND 5),
            R4  INTEGER CHECK(R4 BETWEEN 1 AND 5),
            R5  INTEGER CHECK(R5 BETWEEN 1 AND 5),
            R6  INTEGER CHECK(R6 BETWEEN 1 AND 5),
            R7  INTEGER CHECK(R7 BETWEEN 1 AND 5),
            R8  INTEGER CHECK(R8 BETWEEN 1 AND 5),
            R9  INTEGER CHECK(R9 BETWEEN 1 AND 5),
            R10 INTEGER CHECK(R10 BETWEEN 1 AND 5),

            R11 INTEGER CHECK(R11 BETWEEN 1 AND 5),
            R12 INTEGER CHECK(R12 BETWEEN 1 AND 5),
            R13 INTEGER CHECK(R13 BETWEEN 1 AND 5),
            R14 INTEGER CHECK(R14 BETWEEN 1 AND 5),
            R15 INTEGER CHECK(R15 BETWEEN 1 AND 5),
            R16 INTEGER CHECK(R16 BETWEEN 1 AND 5),
            R17 INTEGER CHECK(R17 BETWEEN 1 AND 5),
            R18 INTEGER CHECK(R18 BETWEEN 1 AND 5),
            R19 INTEGER CHECK(R19 BETWEEN 1 AND 5),
            R20 INTEGER CHECK(R20 BETWEEN 1 AND 5),

            R21 INTEGER CHECK(R21 BETWEEN 1 AND 5),
            R22 INTEGER CHECK(R22 BETWEEN 1 AND 5),
            R23 INTEGER CHECK(R23 BETWEEN 1 AND 5),
            R24 INTEGER CHECK(R24 BETWEEN 1 AND 5),
            R25 INTEGER CHECK(R25 BETWEEN 1 AND 5),
            R26 INTEGER CHECK(R26 BETWEEN 1 AND 5),
            R27 INTEGER CHECK(R27 BETWEEN 1 AND 5),
            R28 INTEGER CHECK(R28 BETWEEN 1 AND 5),
            R29 INTEGER CHECK(R29 BETWEEN 1 AND 5),
            R30 INTEGER CHECK(R30 BETWEEN 1 AND 5),

            R31 INTEGER CHECK(R31 BETWEEN 1 AND 5),
            R32 INTEGER CHECK(R32 BETWEEN 1 AND 5),
            R33 INTEGER CHECK(R33 BETWEEN 1 AND 5),
            R34 INTEGER CHECK(R34 BETWEEN 1 AND 5),
            R35 INTEGER CHECK(R35 BETWEEN 1 AND 5),
            R36 INTEGER CHECK(R36 BETWEEN 1 AND 5),
            R37 INTEGER CHECK(R37 BETWEEN 1 AND 5),
            R38 INTEGER CHECK(R38 BETWEEN 1 AND 5),
            R39 INTEGER CHECK(R39 BETWEEN 1 AND 5),
            R40 INTEGER CHECK(R40 BETWEEN 1 AND 5),

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

# =============================
# AUTH DECORATORS
# =============================
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
                return "Forbidden", 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# =============================
# AUTH ROUTES
# =============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_user(username)

        if not user or not check_password_hash(user["password_hash"], password):
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

# =============================
# MAIN UI
# =============================
@app.get("/")
@login_required
def home():
    return render_template(
        "index.html",
        username=session.get("username"),
        role=session.get("role")
    )

# =============================
# API ROUTES (PLAIN TEXT)
# =============================
@app.post("/api/ingest")
@login_required
@role_required("admin")
def api_ingest():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    source = (data.get("source") or "manual").strip()

    if not text:
        return "Error: text is empty", 400

    try:
        n = ingest_text(text, source=source)

        log_interaction(
            role="admin",
            action="ingest",
            user_input=f"source={source}",
            output=f"chunks_added={n}",
            approved=1
        )

        return f"OK: Ingested {n} chunks from {source}"
    except Exception as e:
        return f"Error: {e}", 500


@app.post("/api/chat")
@login_required
def api_chat():
    try:
        payload = request.get_json(force=True, silent=True) or {}
        req = ChatRequest(**payload)
    except ValidationError as e:
        return f"Validation error: {e}", 400
    except Exception as e:
        return f"Error parsing request: {e}", 400

    try:
        out = tutor_chat(req.message)

        log_interaction(
            role=session.get("role"),
            action="chat",
            user_input=req.message,
            output=out,
            approved=0
        )

        return out
    except Exception as e:
        return f"Error in chat engine: {e}", 500


@app.post("/api/lesson")
@login_required
@role_required("admin", "lecturer")
def api_lesson():
    try:
        payload = request.get_json(force=True, silent=True) or {}
        req = LessonRequest(**payload)
    except ValidationError as e:
        return f"Validation error: {e}", 400
    except Exception as e:
        return f"Error parsing request: {e}", 400

    try:
        out = generate_lesson_plan(
            topic=req.topic,
            level=req.level,
            subject=req.subject,
            duration_min=req.duration_min
        )

        log_interaction(
            role=session.get("role"),
            action="lesson_plan",
            user_input=f"{req.subject} | {req.topic}",
            output=out,
            approved=0
        )

        return out
    except Exception as e:
        return f"Error generating lesson: {e}", 500


@app.post("/api/feedback")
@login_required
@role_required("admin", "lecturer")
def api_feedback():
    try:
        payload = request.get_json(force=True, silent=True) or {}
        req = FeedbackRequest(**payload)
    except ValidationError as e:
        return f"Validation error: {e}", 400
    except Exception as e:
        return f"Error parsing request: {e}", 400

    try:
        out = rubric_feedback(req.lesson_text, req.rubric_text)

        log_interaction(
            role=session.get("role"),
            action="rubric_feedback",
            user_input="lesson+rubric",
            output=out,
            approved=0
        )

        return out
    except Exception as e:
        return f"Error generating feedback: {e}", 500


@app.get("/api/logs")
@login_required
@role_required("admin")
def api_logs():
    try:
        rows = recent_logs(30)
        if not rows:
            return "No logs yet."

        lines = []
        for r in rows:
            _id, ts, role, action, approved, reviewer, inp, outp = r
            lines.append(
                f"- id={_id} | {ts} | {role} | {action} | approved={approved}\n"
                f"  in: {inp}\n"
                f"  out: {outp}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading logs: {e}", 500



# =============================
# SURVEY ROUTES
# =============================
@app.post("/api/survey/submit")
@login_required
def submit_survey():
    if session.get("role") not in ("student", "lecturer", "admin"):
        return "Forbidden", 403

    data = request.get_json(force=True, silent=True)
    if not data:
        return "Invalid JSON payload", 400

    role = data.get("role") or session.get("role")

    responses = {}
    for i in range(1, 41):
        key = f"R{i}"
        if key not in data:
            return f"Missing {key}", 400
        try:
            v = int(data[key])
        except Exception:
            return f"Invalid value for {key}", 400
        if v < 1 or v > 5:
            return f"{key} must be between 1 and 5", 400
        responses[key] = v

    try:
        conn = survey_db()
        cur = conn.cursor()

        columns = ", ".join(responses.keys())
        placeholders = ", ".join(["?"] * len(responses))

        sql = f"""
            INSERT INTO likert_responses
            ({columns}, role, created_at)
            VALUES ({placeholders}, ?, ?)
        """

        cur.execute(
            sql,
            (*responses.values(), role, datetime.utcnow().isoformat())
        )

        conn.commit()
        conn.close()
        return "Survey submitted successfully"

    except Exception as e:
        return f"Survey error: {e}", 500



import statistics

@app.get("/api/survey/analysis")
@login_required
@role_required("admin")
def survey_analysis():
    try:
        conn = survey_db()
        cur = conn.cursor()

        # Fetch all R1–R40 values
        cur.execute("""
            SELECT
                R1, R2, R3, R4, R5, R6, R7, R8, R9, R10,
                R11, R12, R13, R14, R15, R16, R17, R18, R19, R20,
                R21, R22, R23, R24, R25, R26, R27, R28, R29, R30,
                R31, R32, R33, R34, R35, R36, R37, R38, R39, R40
            FROM likert_responses
        """)

        rows = cur.fetchall()
        conn.close()

        if not rows:
            return "No survey data yet"

        # Flatten all responses into a single list
        scores = []
        for row in rows:
            for v in row:
                if v is not None:
                    scores.append(int(v))

        if not scores:
            return "No valid responses yet"

        mean = round(statistics.mean(scores), 2)

        if mean >= 4.5:
            insight = "Strongly positive perception"
        elif mean >= 3.5:
            insight = "Moderate acceptance"
        elif mean >= 2.5:
            insight = "Neutral perception"
        else:
            insight = "Negative perception"

        return (
            f"Survey Count (Respondents): {len(rows)}\n"
            f"Total Responses: {len(scores)}\n"
            f"Overall Mean Score: {mean}\n"
            f"Insight: {insight}\n"
        )

    except Exception as e:
        return f"Analysis error: {e}", 500




@app.get("/api/survey/export")
@login_required
@role_required("admin")   # ✅ admin only
def export_survey():
    try:
        conn = survey_db()
        cur = conn.cursor()

        # Explicit column order (important for Excel / SPSS / ML)
        cur.execute("""
            SELECT
                id,
                R1, R2, R3, R4, R5, R6, R7, R8, R9, R10,
                R11, R12, R13, R14, R15, R16, R17, R18, R19, R20,
                R21, R22, R23, R24, R25, R26, R27, R28, R29, R30,
                R31, R32, R33, R34, R35, R36, R37, R38, R39, R40,
                role,
                created_at
            FROM likert_responses
            ORDER BY id ASC
        """)

        rows = cur.fetchall()
        conn.close()

        import csv
        with open(EXPORT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id",
                *[f"R{i}" for i in range(1, 41)],
                "role",
                "created_at"
            ])
            for row in rows:
                writer.writerow(row)

        return send_file(EXPORT_CSV, as_attachment=True)

    except Exception as e:
        return f"Export error: {e}", 500

# =============================
# ADMIN USER MANAGEMENT
# =============================
@app.get("/admin/users")
@login_required
@role_required("admin")
def admin_users():
    conn = user_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created_at FROM users ORDER BY role, username")
    users = cur.fetchall()
    conn.close()

    return render_template(
        "admin_users.html",
        users=users,
        username=session.get("username"),
        role=session.get("role")
    )


@app.post("/admin/users/create")
@login_required
@role_required("admin")
def admin_create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role")

    if not username or not password or role not in ("admin", "lecturer", "student"):
        flash("Invalid input", "error")
        return redirect(url_for("admin_users"))

    try:
        conn = user_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
        """, (username, generate_password_hash(password), role, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        flash(f"User '{username}' created as {role}.", "success")
    except sqlite3.IntegrityError:
        flash("Username already exists", "error")
    except Exception as e:
        flash(f"Error: {e}", "error")

    return redirect(url_for("admin_users"))


@app.post("/admin/users/delete/<int:user_id>")
@login_required
@role_required("admin")
def admin_delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot delete your own account", "error")
        return redirect(url_for("admin_users"))

    try:
        conn = user_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        flash("User deleted successfully", "success")
    except Exception as e:
        flash(f"Error deleting user: {e}", "error")

    return redirect(url_for("admin_users"))

# =============================
# CHANGE PASSWORD
# =============================
@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")

        if not old or not new:
            flash("Both old and new password are required", "error")
            return redirect(url_for("change_password"))

        user = get_user_by_id(session["user_id"])
        if not user or not check_password_hash(user["password_hash"], old):
            flash("Old password incorrect", "error")
            return redirect(url_for("change_password"))

        try:
            conn = user_db()
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (generate_password_hash(new), session["user_id"])
            )
            conn.commit()
            conn.close()
            flash("Password updated successfully", "success")
            return redirect(url_for("home"))
        except Exception as e:
            flash(f"Error updating password: {e}", "error")
            return redirect(url_for("change_password"))

    return render_template("change_password.html")




@app.get("/api/survey/responses")
@login_required
@role_required("admin")
def survey_responses():
    page = int(request.args.get("page", 1))
    per_page = 10
    offset = (page - 1) * per_page

    conn = survey_db()
    cur = conn.cursor()

    # total count
    cur.execute("SELECT COUNT(*) FROM likert_responses")
    total = cur.fetchone()[0]

    # paginated data
    cur.execute(f"""
        SELECT
            id,
            R1, R2, R3, R4, R5,
            R6, R7, R8, R9, R10,
            role,
            created_at
        FROM likert_responses
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))

    rows = cur.fetchall()
    conn.close()

    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
        "data": rows
    }












# =============================
# ENTRY POINT
# =============================
# if __name__ == "__main__":
#     init_users_db()
#     init_survey_db()
#     app.run(host="127.0.0.1", port=5000, debug=True,use_reloader=False)
init_users_db()
init_survey_db()

if __name__ == "__main__":
    app.run(debug=True)