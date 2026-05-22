"""
YouTube Clipper Web — FastAPI backend
"""

import os
import uuid
import sqlite3
import json
import asyncio
import shutil
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException, Cookie
from fastapi.responses import (
    HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
)
from fastapi.templating import Jinja2Templates

import clipper as clipper_mod

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────
SECRET_KEY      = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD", "admin123")
DB_PATH         = os.environ.get("DB_PATH", "clipper.db")
CLIPS_BASE_DIR  = os.environ.get("CLIPS_DIR", "clips")
CLIP_TTL_HOURS  = 24
COOKIE_NAME     = "session"
TOKEN_EXP_HOURS = 8

# ── In-memory progress store ─────────────────────────────────────────────────
# job_id → {"percent": int, "message": str, "done": bool, "error": str|None}
_progress: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=3)


# ── Database ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    UNIQUE NOT NULL,
            pw_hash  TEXT    NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT  DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id         TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            youtube_url TEXT NOT NULL,
            min_dur    INTEGER NOT NULL,
            max_dur    INTEGER NOT NULL,
            status     TEXT DEFAULT 'pending',
            error_msg  TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            done_at    TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS clips (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT NOT NULL,
            user_id     INTEGER NOT NULL,
            clip_number INTEGER,
            title       TEXT,
            hashtags    TEXT,
            hook        TEXT,
            reason      TEXT,
            filename    TEXT,
            duration    INTEGER,
            expires_at  TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );
        """)
        # Create admin if missing
        admin = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not admin:
            pw_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
            db.execute(
                "INSERT INTO users (username, pw_hash, is_admin) VALUES (?,?,1)",
                ("admin", pw_hash),
            )
            db.commit()


def cleanup_expired_clips():
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        expired = db.execute(
            "SELECT job_id, filename FROM clips WHERE expires_at < ?", (now,)
        ).fetchall()
        for row in expired:
            clip_dir = os.path.join(CLIPS_BASE_DIR, row["job_id"])
            clip_path = os.path.join(clip_dir, row["filename"])
            if os.path.exists(clip_path):
                os.remove(clip_path)
        if expired:
            db.execute("DELETE FROM clips WHERE expires_at < ?", (now,))
            db.commit()


# ── Auth helpers ─────────────────────────────────────────────────────────────
def make_token(user_id: int, username: str, is_admin: bool) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXP_HOURS)
    return jwt.encode(
        {"sub": user_id, "username": username, "is_admin": is_admin, "exp": exp},
        SECRET_KEY, algorithm="HS256",
    )


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def current_user(session: Optional[str] = Cookie(default=None)) -> Optional[dict]:
    if not session:
        return None
    return decode_token(session)


def require_user(session: Optional[str] = Cookie(default=None)) -> dict:
    user = current_user(session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(session: Optional[str] = Cookie(default=None)) -> dict:
    user = require_user(session)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ── Background job runner ─────────────────────────────────────────────────────
def _run_job_thread(job_id: str, user_id: int, youtube_url: str, min_dur: int, max_dur: int):
    _progress[job_id] = {"percent": 0, "message": "Đang khởi động…", "done": False, "error": None}

    def progress(msg: str, pct: int):
        _progress[job_id]["message"] = msg
        _progress[job_id]["percent"] = pct

    work_dir  = os.path.join(CLIPS_BASE_DIR, job_id, "_work")
    out_dir   = os.path.join(CLIPS_BASE_DIR, job_id)

    try:
        results = clipper_mod.run_job(
            youtube_url, min_dur, max_dur, work_dir, out_dir, ANTHROPIC_KEY, progress
        )
        expires = (datetime.now(timezone.utc) + timedelta(hours=CLIP_TTL_HOURS)).isoformat()
        with get_db() as db:
            for clip in results:
                db.execute(
                    """INSERT INTO clips
                       (job_id, user_id, clip_number, title, hashtags, hook, reason, filename, duration, expires_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (job_id, user_id, clip["clip_number"], clip["title"],
                     clip["hashtags"], clip["hook"], clip["reason"],
                     clip["filename"], clip["duration"], expires),
                )
            db.execute(
                "UPDATE jobs SET status='done', done_at=datetime('now') WHERE id=?",
                (job_id,)
            )
            db.commit()
        _progress[job_id]["done"] = True
        _progress[job_id]["percent"] = 100
        _progress[job_id]["message"] = f"Xong! Đã tạo {len(results)} clip."

    except Exception as exc:
        err = str(exc)
        with get_db() as db:
            db.execute(
                "UPDATE jobs SET status='error', error_msg=? WHERE id=?",
                (err[:500], job_id)
            )
            db.commit()
        _progress[job_id]["done"] = True
        _progress[job_id]["error"] = err
        _progress[job_id]["message"] = f"Lỗi: {err[:200]}"


# ── App lifecycle ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(CLIPS_BASE_DIR, exist_ok=True)
    init_db()
    cleanup_expired_clips()
    yield
    _executor.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


# ── Routes: Auth ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(session: Optional[str] = Cookie(default=None)):
    if current_user(session):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
    if not user or not bcrypt.checkpw(password.encode(), user["pw_hash"].encode()):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Tên đăng nhập hoặc mật khẩu không đúng"},
            status_code=401,
        )
    token = make_token(user["id"], user["username"], bool(user["is_admin"]))
    resp = RedirectResponse("/dashboard", status_code=302)
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=TOKEN_EXP_HOURS * 3600)
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ── Routes: Dashboard ─────────────────────────────────────────────────────────
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user:
        return RedirectResponse("/login", status_code=302)

    with get_db() as db:
        jobs = db.execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
            (user["sub"],)
        ).fetchall()
        clips = db.execute(
            "SELECT c.*, j.youtube_url FROM clips c JOIN jobs j ON c.job_id=j.id "
            "WHERE c.user_id=? ORDER BY c.id DESC",
            (user["sub"],)
        ).fetchall()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "jobs": [dict(j) for j in jobs],
        "clips": [dict(c) for c in clips],
    })


@app.post("/api/clip")
async def submit_clip(
    youtube_url: str = Form(...),
    duration: str = Form(...),
    session: Optional[str] = Cookie(default=None),
):
    user = current_user(session)
    if not user:
        raise HTTPException(status_code=401)

    duration_map = {
        "1": (15,  59),
        "2": (60,  90),
        "3": (90,  120),
        "4": (120, 300),
    }
    min_dur, max_dur = duration_map.get(duration, (60, 90))

    job_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO jobs (id, user_id, youtube_url, min_dur, max_dur, status) VALUES (?,?,?,?,?,?)",
            (job_id, user["sub"], youtube_url, min_dur, max_dur, "processing"),
        )
        db.commit()

    _executor.submit(_run_job_thread, job_id, user["sub"], youtube_url, min_dur, max_dur)

    return RedirectResponse(f"/job/{job_id}", status_code=302)


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_page(job_id: str, request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user:
        return RedirectResponse("/login", status_code=302)

    with get_db() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["sub"])
        ).fetchone()
    if not job:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse("job.html", {
        "request": request,
        "user": user,
        "job": dict(job),
    })


@app.get("/api/progress/{job_id}")
async def progress_stream(job_id: str, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user:
        raise HTTPException(status_code=401)

    async def generate():
        # Wait up to 30 s for job to appear in progress store
        for _ in range(60):
            if job_id in _progress:
                break
            await asyncio.sleep(0.5)
            yield f"data: {json.dumps({'percent': 0, 'message': 'Đang khởi động…', 'done': False})}\n\n"

        while True:
            state = _progress.get(job_id, {})
            yield f"data: {json.dumps(state)}\n\n"
            if state.get("done"):
                break
            await asyncio.sleep(0.8)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/job/{job_id}/clips")
async def job_clips(job_id: str, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user:
        raise HTTPException(status_code=401)
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM clips WHERE job_id=? AND user_id=?",
            (job_id, user["sub"])
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/download/{job_id}/{filename}")
async def download_clip(
    job_id: str, filename: str, session: Optional[str] = Cookie(default=None)
):
    user = current_user(session)
    if not user:
        raise HTTPException(status_code=401)
    with get_db() as db:
        clip = db.execute(
            "SELECT * FROM clips WHERE job_id=? AND filename=? AND user_id=?",
            (job_id, filename, user["sub"])
        ).fetchone()
    if not clip:
        raise HTTPException(status_code=404)
    path = os.path.join(CLIPS_BASE_DIR, job_id, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File đã hết hạn")
    return FileResponse(path, media_type="video/mp4", filename=filename)


# ── Routes: Admin ─────────────────────────────────────────────────────────────
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, session: Optional[str] = Cookie(default=None)):
    user = current_user(session)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    with get_db() as db:
        users = db.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY id").fetchall()
        jobs  = db.execute(
            "SELECT j.*, u.username FROM jobs j JOIN users u ON j.user_id=u.id ORDER BY j.created_at DESC LIMIT 50"
        ).fetchall()
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": user,
        "users": [dict(u) for u in users],
        "jobs":  [dict(j) for j in jobs],
    })


@app.post("/admin/users/create")
async def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str = Form(default="0"),
    session: Optional[str] = Cookie(default=None),
):
    user = current_user(session)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=403)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users (username, pw_hash, is_admin) VALUES (?,?,?)",
                (username, pw_hash, 1 if is_admin == "1" else 0),
            )
            db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")
    return RedirectResponse("/admin", status_code=302)


@app.post("/admin/users/delete")
async def admin_delete_user(
    user_id: int = Form(...),
    session: Optional[str] = Cookie(default=None),
):
    user = current_user(session)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=403)
    if user_id == user["sub"]:
        raise HTTPException(status_code=400, detail="Không thể xóa chính mình")
    with get_db() as db:
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()
    return RedirectResponse("/admin", status_code=302)
