from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timezone
import sqlite3
import os
import secrets
import hmac
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "parking.db"
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            zone TEXT NOT NULL,
            hourly_rate INTEGER NOT NULL CHECK(hourly_rate >= 0),
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            slot_id INTEGER NOT NULL REFERENCES slots(id),
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed'
              CHECK(status IN ('confirmed', 'cancelled')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(start_at < end_at)
        );
        CREATE INDEX IF NOT EXISTS reservation_slot_time_idx
          ON reservations(slot_id, start_at, end_at, status);
        """)
        if db.execute("SELECT COUNT(*) FROM slots").fetchone()[0] == 0:
            for i in range(1, 13):
                db.execute("INSERT INTO slots(code, zone, hourly_rate) VALUES (?, ?, ?)",
                           (f"A-{i:02d}", "A" if i <= 6 else "B", 30))

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]

@app.context_processor
def inject_csrf():
    return {"csrf_token": csrf_token}

@app.before_request
def protect_post_requests():
    if request.method == "POST":
        expected = session.get("_csrf", "")
        supplied = request.form.get("_csrf", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            if request.is_json:
                return jsonify(error="Security token missing or invalid. Refresh and try again."), 403
            flash("Security token expired. Please try again.", "error")
            return redirect(url_for("index"))

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped

def parse_time(value):
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            # Browser datetime-local values are treated as local wall time.
            dt = dt.astimezone()
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None

def validate_range(start_raw, end_raw):
    start, end = parse_time(start_raw), parse_time(end_raw)
    now = datetime.now(timezone.utc)
    if not start or not end:
        return None, None, "Choose valid start and end times."
    if start.timestamp() < now.timestamp() - 60:
        return None, None, "Start time must be in the future."
    if end <= start:
        return None, None, "End time must be after start time."
    if (end - start).total_seconds() > 24 * 3600:
        return None, None, "Reservations are limited to 24 hours."
    # ISO strings in UTC sort lexicographically and consistently in SQLite.
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"), None

def slot_availability(start_at, end_at):
    with get_db() as db:
        return db.execute("""
            SELECT s.id, s.code, s.zone, s.hourly_rate,
              CASE WHEN EXISTS (
                SELECT 1 FROM reservations r
                WHERE r.slot_id=s.id AND r.status='confirmed'
                  AND r.start_at < ? AND r.end_at > ?
              ) THEN 0 ELSE 1 END AS available
            FROM slots s WHERE s.active=1 ORDER BY s.zone, s.code
        """, (end_at, start_at)).fetchall()

@app.get("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.post("/register")
def register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not re.fullmatch(r"[\w .'-]{2,60}", name, flags=re.UNICODE):
        flash("Name must be 2–60 characters and use ordinary letters, numbers, spaces, . ' or -.", "error")
        return redirect(url_for("index"))
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        flash("Enter a valid email address.", "error")
        return redirect(url_for("index"))
    if len(password) < 8 or len(password) > 128:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("index"))
    try:
        with get_db() as db:
            cur = db.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                             (name, email, generate_password_hash(password)))
            user_id = cur.lastrowid
        session.clear()
        session["user_id"] = user_id
        session["name"] = name
        session["_csrf"] = secrets.token_urlsafe(32)
        return redirect(url_for("dashboard"))
    except sqlite3.IntegrityError:
        flash("An account with that email already exists.", "error")
        return redirect(url_for("index"))

@app.post("/login")
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.", "error")
        return redirect(url_for("index"))
    session.clear()  # rotate session contents after successful authentication
    session["user_id"] = user["id"]
    session["name"] = user["name"]
    session["_csrf"] = secrets.token_urlsafe(32)
    return redirect(url_for("dashboard"))

@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("index"))

@app.get("/dashboard")
@login_required
def dashboard():
    # Defaults are set in the browser; availability is fetched after choosing times.
    return render_template("dashboard.html", name=session.get("name", "Driver"))

@app.get("/api/slots")
@login_required
def api_slots():
    start_raw, end_raw = request.args.get("start", ""), request.args.get("end", "")
    start, end, error = validate_range(start_raw, end_raw)
    if error:
        return jsonify(error=error), 400
    rows = slot_availability(start, end)
    return jsonify(slots=[dict(id=r["id"], code=r["code"], zone=r["zone"],
                               hourlyRate=r["hourly_rate"], available=bool(r["available"])) for r in rows])

@app.post("/reserve")
@login_required
def reserve():
    slot_id = request.form.get("slot_id", type=int)
    start, end, error = validate_range(request.form.get("start_at", ""), request.form.get("end_at", ""))
    if error or not slot_id:
        flash(error or "Choose a valid parking slot.", "error")
        return redirect(url_for("dashboard"))
    try:
        # BEGIN IMMEDIATE obtains the SQLite write lock before availability is checked.
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        slot = db.execute("SELECT id, code, hourly_rate FROM slots WHERE id=? AND active=1", (slot_id,)).fetchone()
        if not slot:
            db.rollback()
            flash("Parking slot not found.", "error")
            return redirect(url_for("dashboard"))
        overlap = db.execute("""
            SELECT id FROM reservations
            WHERE slot_id=? AND status='confirmed' AND start_at < ? AND end_at > ?
            LIMIT 1
        """, (slot_id, end, start)).fetchone()
        if overlap:
            db.rollback()
            flash("This slot was just reserved for that time. Please choose another.", "error")
            return redirect(url_for("dashboard"))
        start_dt, end_dt = datetime.fromisoformat(start), datetime.fromisoformat(end)
        hours = (end_dt - start_dt).total_seconds() / 3600
        cost = int(hours * slot["hourly_rate"] + 0.999999)
        db.execute("INSERT INTO reservations(user_id,slot_id,start_at,end_at) VALUES(?,?,?,?)",
                   (session["user_id"], slot_id, start, end))
        db.commit()
        flash(f"Reservation confirmed for {slot['code']}. Estimated cost: ₹{cost}.", "success")
    except sqlite3.Error:
        try: db.rollback()
        except Exception: pass
        app.logger.exception("Reservation database error")
        flash("Reservation could not be completed. Please try again.", "error")
    finally:
        try: db.close()
        except Exception: pass
    return redirect(url_for("dashboard"))

@app.post("/cancel/<int:reservation_id>")
@login_required
def cancel(reservation_id):
    with get_db() as db:
        result = db.execute("""
            UPDATE reservations SET status='cancelled'
            WHERE id=? AND user_id=? AND status='confirmed' AND start_at > ?
        """, (reservation_id, session["user_id"], datetime.now(timezone.utc).isoformat(timespec="seconds")))
    if result.rowcount:
        flash("Reservation cancelled.", "success")
    else:
        flash("Reservation not found, already cancelled, or already started.", "error")
    return redirect(url_for("dashboard"))

@app.get("/api/reservations")
@login_required
def api_reservations():
    with get_db() as db:
        rows = db.execute("""
            SELECT r.id, r.start_at, r.end_at, r.status, s.code, s.zone, s.hourly_rate
            FROM reservations r JOIN slots s ON s.id=r.slot_id
            WHERE r.user_id=? ORDER BY r.created_at DESC
        """, (session["user_id"],)).fetchall()
    return jsonify(reservations=[dict(id=r["id"], startAt=r["start_at"], endAt=r["end_at"],
        status=r["status"], code=r["code"], zone=r["zone"], hourlyRate=r["hourly_rate"]) for r in rows])

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response

init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
