from dataclasses import dataclass
from pathlib import Path
from flask import Flask, jsonify, request, Blueprint, g, send_from_directory, abort
import datetime as dt
import json
import logging
import os
import hmac
import re
import hashlib
import math
import secrets
import time
import uuid
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from typing import Dict, Any, List, Optional
from werkzeug.exceptions import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_BUILD_DIR = BASE_DIR.parent / "frontend" / "build"
DEFAULT_FRONTEND_ORIGINS = {"http://localhost:3000", "http://localhost:3002", "http://127.0.0.1:3000", "http://127.0.0.1:3002"}
SESSION_COOKIE_NAME = "gluverse_session"
CSRF_COOKIE_NAME = "gluverse_csrf"
DEFAULT_COOKIE_SAMESITE = "Lax"


@dataclass(frozen=True)
class Config:
    app_env: str
    flask_debug: bool
    secret_key: str
    database_url: str
    cors_origins: set[str]
    log_level: str
    port: int
    token_ttl_minutes: int
    request_timeout_seconds: int
    demo_reset_enabled: bool
    gunicorn_workers: int
    gunicorn_threads: int
    gunicorn_timeout: int
    session_ttl_minutes: int
    cookie_secure: bool
    nvidia_api_key: str = ""
    nvidia_api_base_url: str = ""
    nvidia_coach_model: str = ""
    nvidia_safety_model: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


def _parse_bool(value: str, field_name: str, default: bool) -> bool:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean for {field_name}: {value!r}")


def to_bool(value, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean.")
    return value


def _parse_int(value: str, field_name: str, default: Optional[int] = None, minimum: Optional[int] = None) -> int:
    if value is None or value == "":
        if default is None:
            raise RuntimeError(f"Missing required configuration: {field_name}")
        number = default
    else:
        try:
            number = int(value)
        except ValueError as exc:
            raise RuntimeError(f"Invalid integer for {field_name}: {value!r}") from exc
    if minimum is not None and number < minimum:
        raise RuntimeError(f"{field_name} must be at least {minimum}")
    return number


def _resolve_database_url(database_url: str) -> str:
    if database_url and "://" not in database_url:
        absolute = Path(database_url).resolve()
        return f"sqlite:///{absolute}"
    if database_url.startswith("sqlite:///"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def sanitize_database_url(database_url: str) -> str:
    if "://" not in database_url:
        return database_url
    parsed = urlsplit(database_url)
    if not parsed.password:
        return database_url
    username = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{username}:***@{host}{port}" if username else f"***@{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def load_config() -> Config:
    app_env = os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "development"
    flask_debug = _parse_bool(os.environ.get("FLASK_DEBUG"), "FLASK_DEBUG", default=(app_env != "production"))
    secret_key = os.environ.get("SECRET_KEY", "")
    database_url = os.environ.get("DATABASE_URL", "")
    cors_raw = os.environ.get("CORS_ORIGINS", "")
    log_level = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    port = _parse_int(os.environ.get("PORT"), "PORT", default=5000, minimum=1)
    token_ttl_minutes = _parse_int(os.environ.get("TOKEN_TTL_MINUTES"), "TOKEN_TTL_MINUTES", default=60 if app_env == "production" else 60, minimum=5)
    request_timeout_seconds = _parse_int(os.environ.get("REQUEST_TIMEOUT_SECONDS"), "REQUEST_TIMEOUT_SECONDS", default=15, minimum=1)
    demo_reset_enabled = _parse_bool(os.environ.get("DEMO_RESET_ENABLED"), "DEMO_RESET_ENABLED", default=(app_env != "production"))
    gunicorn_workers = _parse_int(os.environ.get("GUNICORN_WORKERS"), "GUNICORN_WORKERS", default=1, minimum=1)
    gunicorn_threads = _parse_int(os.environ.get("GUNICORN_THREADS"), "GUNICORN_THREADS", default=4, minimum=1)
    gunicorn_timeout = _parse_int(os.environ.get("GUNICORN_TIMEOUT"), "GUNICORN_TIMEOUT", default=60, minimum=1)
    session_ttl_minutes = _parse_int(os.environ.get("SESSION_TTL_MINUTES"), "SESSION_TTL_MINUTES", default=60, minimum=5)
    cookie_secure = _parse_bool(os.environ.get("COOKIE_SECURE"), "COOKIE_SECURE", default=(app_env == "production"))
    nvidia_api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    nvidia_api_base_url = os.environ.get("NVIDIA_API_BASE_URL", "").strip() or "https://integrate.api.nvidia.com/v1/chat/completions"
    nvidia_coach_model = os.environ.get("NVIDIA_COACH_MODEL", "").strip()
    nvidia_safety_model = os.environ.get("NVIDIA_SAFETY_MODEL", "").strip()

    if app_env == "production":
        missing = [name for name, val in [("SECRET_KEY", secret_key), ("DATABASE_URL", database_url), ("CORS_ORIGINS", cors_raw)] if not val]
        if missing:
            raise RuntimeError(f"Missing required production configuration: {', '.join(missing)}")
        if len(secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters in production.")
        if not database_url.startswith("postgresql://") and not database_url.startswith("postgresql+psycopg://"):
            raise RuntimeError("Production DATABASE_URL must point to PostgreSQL.")

    if not nvidia_api_key or not nvidia_coach_model or not nvidia_safety_model:
        raise RuntimeError("Missing required NVIDIA configuration: NVIDIA_API_KEY, NVIDIA_COACH_MODEL, NVIDIA_SAFETY_MODEL")

    cors_origins = set(filter(None, (origin.strip() for origin in cors_raw.split(",")))) or DEFAULT_FRONTEND_ORIGINS
    if not cors_origins:
        cors_origins = DEFAULT_FRONTEND_ORIGINS

    return Config(
        app_env=app_env,
        flask_debug=flask_debug,
        secret_key=secret_key or "dev-only-insecure-secret",
        database_url=_resolve_database_url(database_url or str(BASE_DIR / "gluverse.db")),
        cors_origins=cors_origins,
        log_level=log_level,
        port=port,
        token_ttl_minutes=token_ttl_minutes,
        request_timeout_seconds=request_timeout_seconds,
        demo_reset_enabled=demo_reset_enabled,
        gunicorn_workers=gunicorn_workers,
        gunicorn_threads=gunicorn_threads,
        gunicorn_timeout=gunicorn_timeout,
        session_ttl_minutes=session_ttl_minutes,
        cookie_secure=cookie_secure,
        nvidia_api_key=nvidia_api_key,
        nvidia_api_base_url=nvidia_api_base_url,
        nvidia_coach_model=nvidia_coach_model,
        nvidia_safety_model=nvidia_safety_model,
    )


CONFIG = load_config()
app = Flask(__name__, static_folder=str(FRONTEND_BUILD_DIR / "static"), static_url_path="/static")
app.config["SECRET_KEY"] = CONFIG.secret_key
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
app.config["SESSION_COOKIE_NAME"] = SESSION_COOKIE_NAME
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = CONFIG.cookie_secure
app.config["SESSION_COOKIE_SAMESITE"] = DEFAULT_COOKIE_SAMESITE
MAX_TEXT_LENGTH = 1000
GLUCOSE_STALE_THRESHOLD_MINUTES = 30
REQUEST_STARTED_AT = "_request_started_at"
REQUEST_ID_HEADER = "X-Request-ID"
_initialized = False
_engine: Optional[Engine] = None
_request_logger = logging.getLogger("gluverse")
if not _request_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _request_logger.addHandler(handler)
_request_logger.setLevel(getattr(logging, CONFIG.log_level, logging.INFO))
_request_logger.propagate = False
_rate_limit_buckets: dict[str, list[float]] = {}
print(json.dumps({
    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    "severity": "INFO",
    "message": "startup_configuration",
    "app_env": CONFIG.app_env,
    "flask_debug": CONFIG.flask_debug,
    "database_url": sanitize_database_url(CONFIG.database_url),
    "cors_origin_count": len(CONFIG.cors_origins),
    "port": CONFIG.port,
    "token_ttl_minutes": CONFIG.token_ttl_minutes,
    "request_timeout_seconds": CONFIG.request_timeout_seconds,
    "demo_reset_enabled": CONFIG.demo_reset_enabled,
    "gunicorn_workers": CONFIG.gunicorn_workers,
    "gunicorn_threads": CONFIG.gunicorn_threads,
    "gunicorn_timeout": CONFIG.gunicorn_timeout,
    "session_ttl_minutes": CONFIG.session_ttl_minutes,
    "cookie_secure": CONFIG.cookie_secure,
    "nvidia_api_base_url": CONFIG.nvidia_api_base_url,
    "nvidia_coach_model": CONFIG.nvidia_coach_model,
    "nvidia_safety_model": CONFIG.nvidia_safety_model,
}))

SHOP_CATALOG = [
    {
        "id": "sensor-pack",
        "name": "Sensor Starter Pack",
        "category": "CGM",
        "price": 129.0,
        "description": "A simple request item for sensors and accessories.",
    },
    {
        "id": "low-snack-kit",
        "name": "Low Snack Kit",
        "category": "Nutrition",
        "price": 24.0,
        "description": "Carb snacks for treating lows and restocking a bag.",
    },
    {
        "id": "travel-case",
        "name": "Travel Case",
        "category": "Supplies",
        "price": 18.0,
        "description": "Compact organizer for meters, sensors, and backup supplies.",
    },
    {
        "id": "care-notebook",
        "name": "Care Notebook",
        "category": "Tracking",
        "price": 12.0,
        "description": "A small logbook for notes, questions, and patterns.",
    },
]


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(value=None):
    return (value or utcnow()).isoformat()


def parse_ts(value: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text.")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset.")
    return parsed


def normalize_timestamp(value, fallback=None):
    if value is None or value == "":
        value = fallback if fallback is not None else iso()
    try:
        parsed = parse_ts(value).astimezone(dt.timezone.utc)
    except OverflowError as exc:
        raise ValueError("timestamp is out of range.") from exc
    if parsed > utcnow() + dt.timedelta(minutes=5):
        raise ValueError("timestamp cannot be more than 5 minutes in the future.")
    return parsed.isoformat()


def parse_json_body(required: bool = True):
    body = request.get_json(silent=True)
    if body is None:
        if required:
            return None, (jsonify({"success": False, "message": "Request body must be valid JSON."}), 400)
        return {}, None
    if not isinstance(body, dict):
        return None, (jsonify({"success": False, "message": "JSON body must be an object."}), 400)
    return body, None


def to_int(value, field_name: str, minimum: Optional[int] = None, maximum: Optional[int] = None):
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field_name} must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}.")
    return number


def to_float(value, field_name: str, minimum: Optional[float] = None):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number.")
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")
    return number


def clamp_text(value, field_name: str, max_length: int = MAX_TEXT_LENGTH):
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field_name} must be text.")
    text = (value or "").strip()
    if len(text) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters.")
    return text


def nvidia_chat_completion(model: str, messages: list[dict[str, str]]) -> str:
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.2}).encode("utf-8")
    request_obj = urllib.request.Request(
        CONFIG.nvidia_api_base_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {CONFIG.nvidia_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request_obj, timeout=CONFIG.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            break
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 0:
                # ponytail: one retry for transient upstream flukes; add jittered backoff if this gets noisy.
                time.sleep(0.2)
    else:
        raise RuntimeError("NVIDIA chat request failed.") from last_error
    data = json.loads(raw or "{}")
    choices = data.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError("NVIDIA chat response was empty.")
    return content


def extract_next_top_5(text: str) -> list[str]:
    lines = [line.strip(" -\t") for line in text.splitlines()]
    items = []
    for line in lines:
        if re.match(r"^\d+[\).\s-]+", line):
            item = re.sub(r"^\d+[\).\s-]+", "", line).strip()
            if item:
                items.append(item)
    return list(dict.fromkeys(items))[:5]


def db():
    global _engine
    if _engine is None:
        if CONFIG.database_url.startswith("sqlite"):
            _engine = create_engine(
                CONFIG.database_url,
                future=True,
                pool_pre_ping=True,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            _engine = create_engine(CONFIG.database_url, future=True, pool_pre_ping=True)
    return _engine.connect()


def is_sqlite() -> bool:
    return CONFIG.database_url.startswith("sqlite")


def conn_execute(conn, query: str, params=()):
    stmt, bound = _sql_text(query, params)
    return conn.execute(stmt, bound)


def _sql_text(query: str, params):
    if not params:
        return text(query), {}
    if isinstance(params, dict):
        return text(query), params
    if "?" not in query:
        return text(query), {}
    named = {}
    parts = query.split("?")
    rebuilt = [parts[0]]
    for idx, part in enumerate(parts[1:]):
        key = f"p{idx}"
        rebuilt.append(f":{key}")
        rebuilt.append(part)
        named[key] = params[idx]
    return text("".join(rebuilt)), named


def insert_ignore(table: str, columns: list[str], values: tuple[Any, ...], conflict_columns: list[str]):
    column_sql = ", ".join(columns)
    placeholder_sql = ", ".join(["?"] * len(columns))
    if is_sqlite():
        execute(f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholder_sql})", values)
        return
    conflict_sql = ", ".join(conflict_columns)
    execute(f"INSERT INTO {table} ({column_sql}) VALUES ({placeholder_sql}) ON CONFLICT ({conflict_sql}) DO NOTHING", values)


def upsert_glucose_seed(row: tuple[Any, ...]):
    columns = ["id", "user_id", "value", "timestamp", "source", "notes", "symptoms", "context", "is_stale", "archived", "created_at"]
    column_sql = ", ".join(columns)
    placeholder_sql = ", ".join(["?"] * len(columns))
    if is_sqlite():
        execute(f"INSERT OR REPLACE INTO glucose_readings ({column_sql}) VALUES ({placeholder_sql})", row)
        return
    update_sql = ", ".join([f"{column} = EXCLUDED.{column}" for column in columns[1:]])
    execute(f"INSERT INTO glucose_readings ({column_sql}) VALUES ({placeholder_sql}) ON CONFLICT (id) DO UPDATE SET {update_sql}", row)


def api_error(message: str, status: int, code: str = "ERROR"):
    return jsonify({
        "success": False,
        "message": message,
        "error": {"code": code, "message": message},
        "request_id": getattr(g, "request_id", None),
    }), status


def check_rate_limit(bucket: str, limit: int, window_seconds: int = 60):
    now = time.time()
    key = f"{bucket}:{request.remote_addr or 'unknown'}"
    entries = [stamp for stamp in _rate_limit_buckets.get(key, []) if now - stamp < window_seconds]
    if len(entries) >= limit:
        _rate_limit_buckets[key] = entries
        return api_error("Too many requests. Please wait and try again.", 429, "RATE_LIMITED")
    entries.append(now)
    _rate_limit_buckets[key] = entries
    return None


def log_event(level: str, message: str, **fields):
    payload = {
        "timestamp": iso(),
        "severity": level.upper(),
        "message": message,
        "app_env": CONFIG.app_env,
        **{k: v for k, v in fields.items() if v is not None},
    }
    _request_logger.log(getattr(logging, level.upper(), logging.INFO), json.dumps(payload, default=str))


def csp_header_value() -> str:
    connect_sources = ["'self'", *sorted(CONFIG.cors_origins)]
    return (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        f"connect-src {' '.join(connect_sources)}"
    )


@app.before_request
def begin_request_context():
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True
    g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    g.request_started_at = time.perf_counter()
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in CONFIG.cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRF-Token, X-Request-ID"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Content-Security-Policy"] = csp_header_value()
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if CONFIG.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers[REQUEST_ID_HEADER] = getattr(g, "request_id", uuid.uuid4().hex)
    if hasattr(g, "request_started_at"):
        duration_ms = round((time.perf_counter() - g.request_started_at) * 1000, 2)
        log_event("info", "request_complete", request_id=response.headers[REQUEST_ID_HEADER], method=request.method, path=request.path, status=response.status_code, duration_ms=duration_ms)
    return response


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    payload = {
        "success": False,
        "error": {
            "code": exc.name.upper().replace(" ", "_"),
            "message": exc.description,
        },
        "request_id": getattr(g, "request_id", None),
    }
    return jsonify(payload), exc.code


@app.errorhandler(Exception)
def handle_unexpected_exception(exc):
    if isinstance(exc, HTTPException):
        return exc
    log_event("error", "unhandled_exception", request_id=getattr(g, "request_id", None), path=request.path if request else None, method=request.method if request else None)
    return jsonify({
        "success": False,
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred.",
        },
        "request_id": getattr(g, "request_id", None),
    }), 500


@app.route("/api/<path:path>", methods=["OPTIONS"])
def cors_preflight(path):
    return ("", 204)


def init_db():
    conn = db()
    if is_sqlite():
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    schema_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            plan TEXT NOT NULL,
            diabetes_type TEXT DEFAULT 'Type 1',
            units TEXT DEFAULT 'mg/dL',
            target_low INTEGER DEFAULT 70,
            target_high INTEGER DEFAULT 180,
            settings_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS glucose_readings (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            value INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            notes TEXT DEFAULT '',
            symptoms TEXT DEFAULT '',
            context TEXT DEFAULT '',
            is_stale INTEGER DEFAULT 0,
            archived INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meals (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            carbs REAL DEFAULT 0,
            protein REAL DEFAULT 0,
            fat REAL DEFAULT 0,
            calories REAL DEFAULT 0,
            timestamp TEXT NOT NULL,
            notes TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS insulin_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            insulin_type TEXT DEFAULT 'bolus',
            units REAL NOT NULL,
            timestamp TEXT NOT NULL,
            notes TEXT DEFAULT '',
            linked_meal_id TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alert_rules (
            user_id TEXT PRIMARY KEY,
            urgent_low INTEGER DEFAULT 54,
            low INTEGER DEFAULT 70,
            high INTEGER DEFAULT 180,
            urgent_high INTEGER DEFAULT 250,
            stale_minutes INTEGER DEFAULT 30,
            missed_meal_hours INTEGER DEFAULT 6,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS achievements (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_achievements (
            user_id TEXT NOT NULL,
            achievement_id TEXT NOT NULL,
            awarded_at TEXT NOT NULL,
            PRIMARY KEY (user_id, achievement_id)
        );
        CREATE TABLE IF NOT EXISTS community_posts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            posted_at TEXT NOT NULL,
            moderated_by TEXT DEFAULT '',
            moderated_at TEXT DEFAULT '',
            hidden_reason TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS community_reports (
            id TEXT PRIMARY KEY,
            post_id TEXT NOT NULL,
            reporter_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cgm_connections (
            user_id TEXT PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'not_connected',
            username TEXT DEFAULT '',
            backend_available INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notification_settings (
            user_id TEXT PRIMARY KEY,
            low_glucose_alert INTEGER DEFAULT 1,
            high_glucose_alert INTEGER DEFAULT 1,
            stale_data_alert INTEGER DEFAULT 1,
            missed_meal_alert INTEGER DEFAULT 0,
            email_enabled INTEGER DEFAULT 0,
            sms_enabled INTEGER DEFAULT 0,
            push_enabled INTEGER DEFAULT 1,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            relationship TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shop_requests (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            item_price REAL NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            notes TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'saved',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            csrf_token TEXT NOT NULL,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT DEFAULT ''
        );
        """
    for statement in [part.strip() for part in schema_sql.split(";") if part.strip()]:
        conn.exec_driver_sql(statement)
    conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower ON users (LOWER(username))")
    conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_shop_requests_user_item ON shop_requests (user_id, item_id)")
    ensure_schema(conn)

    cur = conn.exec_driver_sql("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()[0] == 0 and CONFIG.demo_reset_enabled:
        seed_demo_data(conn)
    conn.close()


def ensure_schema(conn):
    if is_sqlite():
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()}
        session_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sessions)").fetchall()}
    else:
        columns = {row[0] for row in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")).fetchall()}
        session_columns = {row[0] for row in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'sessions'")).fetchall()}
    if "password_hash" not in columns:
        conn.exec_driver_sql("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''")
    if "csrf_token" not in session_columns:
        conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN csrf_token TEXT DEFAULT ''")
    if "revoked_at" not in session_columns:
        conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN revoked_at TEXT DEFAULT ''")
    missing_passwords = conn.execute(text("SELECT COUNT(*) AS c FROM users WHERE password_hash = '' OR password_hash IS NULL")).fetchone()[0]
    if missing_passwords:
        raise RuntimeError("Corrupt user data detected: missing password hashes.")
    conn.commit()


def seed_demo_data(conn):
    now = iso()
    seeds = [
        ("user123", "TestUser", "basic"),
        ("admin123", "AdminUser", "premium"),
    ]
    for u, n, p in seeds:
        conn_execute(conn,
            "INSERT INTO users (id, username, plan, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (u, n, p, hash_password("password123"), now, now),
        )
    for row in [
        ("g1", "user123", 120, now, "manual", "", "", "demo", 0, 0, now),
        ("g2", "user123", 95, iso(utcnow() - dt.timedelta(days=1)), "manual", "", "", "demo", 0, 0, now),
        ("g3", "user123", 150, iso(utcnow() - dt.timedelta(days=2)), "manual", "", "", "demo", 0, 0, now),
    ]:
        conn_execute(conn,
            "INSERT INTO glucose_readings (id, user_id, value, timestamp, source, notes, symptoms, context, is_stale, archived, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
    conn_execute(conn,
        "INSERT INTO meals (id, user_id, name, carbs, protein, fat, calories, timestamp, notes, photo_url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("m1", "user123", "Breakfast", 45, 18, 12, 420, now, "Demo breakfast", "", now),
    )
    for row in [("user123", "week_warrior", now), ("user123", "meal_tracker", now), ("user123", "glucose_guardian", now)]:
        conn_execute(conn, "INSERT INTO user_achievements (user_id, achievement_id, awarded_at) VALUES (?, ?, ?)", row)
    for row in [
        ("c1", "user123", "Hello everyone!", "active", now),
        ("c2", "admin123", "Reminder: keep community posts respectful and safe.", "active", iso(utcnow() - dt.timedelta(days=1))),
    ]:
        conn_execute(conn, "INSERT INTO community_posts (id, user_id, content, status, posted_at) VALUES (?, ?, ?, ?, ?)", row)
    conn_execute(conn, "INSERT INTO alert_rules (user_id, updated_at) VALUES (?, ?)", ("user123", now))
    conn_execute(conn, "INSERT INTO cgm_connections (user_id, state, backend_available, updated_at) VALUES (?, ?, ?, ?)", ("user123", "not_connected", 0, now))
    conn_execute(conn, "INSERT INTO notification_settings (user_id, updated_at) VALUES (?, ?)", ("user123", now))
    for row in [
        ("first_glucose", "First Glucose Log", "Logged your first glucose reading."),
        ("first_meal", "First Meal Log", "Logged your first meal."),
        ("three_day", "3-Day Streak", "Logged glucose for 3 consecutive days."),
        ("seven_day", "7-Day Streak", "Logged glucose for 7 consecutive days."),
        ("ten_meals", "10 Meals", "Logged 10 meals."),
        ("thirty_readings", "30 Readings", "Logged 30 glucose readings."),
    ]:
        conn_execute(conn, "INSERT INTO achievements (id, name, description) VALUES (?, ?, ?)", row)
    conn.commit()

def row_to_dict(row):
    return dict(row) if row else None


def sanitize_user(row):
    if not row:
        return None
    data = dict(row)
    data.pop("password_hash", None)
    return data


def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_session(user_id: str):
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    now = utcnow()
    expires = now + dt.timedelta(minutes=CONFIG.token_ttl_minutes)
    execute(
        "INSERT INTO sessions (token, csrf_token, user_id, created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?)",
        (token, csrf_token, user_id, iso(now), iso(expires), ""),
    )
    return token, csrf_token


def get_user_by_session(token: str):
    session = fetch_one("SELECT * FROM sessions WHERE token = ? AND expires_at > ? AND (revoked_at = '' OR revoked_at IS NULL)", (token, iso()))
    if not session:
        return None
    return get_user(session["user_id"])


def get_session_from_cookie():
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return None
    return fetch_one(
        "SELECT * FROM sessions WHERE token = ? AND expires_at > ? AND (revoked_at = '' OR revoked_at IS NULL)",
        (token, iso()),
    )


def require_current_user():
    session = get_session_from_cookie()
    if not session:
        return None, api_error("Not authenticated.", 401, "AUTH_REQUIRED")
    user = get_user(session["user_id"])
    if not user:
        return None, api_error("Not authenticated.", 401, "AUTH_REQUIRED")
    g.current_session = session
    g.current_user = user
    return user, None


def is_admin_user(user: dict) -> bool:
    return bool(user and user.get("id") == "admin123")


def require_route_user(user_id: str):
    user, error = require_current_user()
    if error:
        return None, error
    if user["id"] != user_id and not is_admin_user(user):
        return None, api_error("You do not have access to this user's data.", 403, "FORBIDDEN")
    return user, None


def require_record_owner(table: str, record_id: str, id_column: str = "id"):
    user, error = require_current_user()
    if error:
        return None, None, error
    row = fetch_one(f"SELECT * FROM {table} WHERE {id_column} = ?", (record_id,))
    if not row:
        return user, None, api_error("Resource not found.", 404, "NOT_FOUND")
    if row.get("user_id") != user["id"] and not is_admin_user(user):
        return user, None, api_error("You do not have access to this resource.", 403, "FORBIDDEN")
    return user, row, None


def set_auth_cookies(response, token: str, csrf_token: str):
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, secure=CONFIG.cookie_secure, samesite=DEFAULT_COOKIE_SAMESITE, max_age=CONFIG.session_ttl_minutes * 60, path="/")
    response.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=False, secure=CONFIG.cookie_secure, samesite=DEFAULT_COOKIE_SAMESITE, max_age=CONFIG.session_ttl_minutes * 60, path="/")
    return response


def clear_auth_cookies(response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return response


def require_csrf():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    if request.endpoint in {"auth_login", "auth_register"}:
        return None
    session = getattr(g, "current_session", None) or get_session_from_cookie()
    if not session:
        return None
    header = request.headers.get("X-CSRF-Token", "")
    if not header or not hmac.compare_digest(header, session["csrf_token"]):
        return api_error("Missing or invalid CSRF token.", 403, "CSRF_INVALID")
    return None


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    limited = check_rate_limit("auth_register", 30)
    if limited:
        return limited
    body, error = parse_json_body()
    if error:
        return error
    try:
        username = clamp_text(body.get("username"), "username", 80)
        password = clamp_text(body.get("password"), "password", 128)
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    if not username or not password:
        return api_error("Username and password are required.", 400, "VALIDATION_ERROR")
    if len(password) < 8:
        return api_error("Password must be at least 8 characters.", 400, "VALIDATION_ERROR")
    existing = get_user_by_username(username)
    if existing:
        return api_error("Username already exists.", 409, "CONFLICT")
    user_id = f"user_{secrets.token_hex(8)}"
    now = iso()
    conn = db()
    try:
        try:
            conn_execute(
                conn,
                "INSERT INTO users (id, username, plan, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, "basic", hash_password(password), now, now),
            )
        except IntegrityError:
            conn.rollback()
            return api_error("Username already exists.", 409, "CONFLICT")
        conn_execute(conn, "INSERT INTO alert_rules (user_id, updated_at) VALUES (?, ?)", (user_id, now))
        conn_execute(conn, "INSERT INTO notification_settings (user_id, updated_at) VALUES (?, ?)", (user_id, now))
        conn_execute(conn, "INSERT INTO cgm_connections (user_id, state, backend_available, updated_at) VALUES (?, ?, ?, ?)", (user_id, "not_connected", 0, now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    token, csrf_token = create_session(user_id)
    response = jsonify({"success": True, "user": sanitize_user(get_user(user_id)), "csrf_token": csrf_token})
    return set_auth_cookies(response, token, csrf_token)


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    limited = check_rate_limit("auth_login", 60)
    if limited:
        return limited
    body, error = parse_json_body()
    if error:
        return error
    try:
        username = clamp_text(body.get("username"), "username", 80)
        password = clamp_text(body.get("password"), "password", 128)
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    user = get_user_by_username(username)
    if not user or not verify_password(password, user.get("password_hash") or ""):
        return api_error("Invalid credentials.", 401, "INVALID_CREDENTIALS")
    token, csrf_token = create_session(user["id"])
    response = jsonify({"success": True, "user": sanitize_user(user), "csrf_token": csrf_token})
    return set_auth_cookies(response, token, csrf_token)


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    session = get_session_from_cookie()
    user = get_user(session["user_id"]) if session else None
    if not user:
        return api_error("Not authenticated.", 401, "AUTH_REQUIRED")
    return jsonify({"success": True, "user": sanitize_user(user), "csrf_token": session["csrf_token"]})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session = get_session_from_cookie()
    if session:
        execute("UPDATE sessions SET revoked_at = ? WHERE token = ?", (iso(), session["token"]))
    response = jsonify({"success": True})
    return clear_auth_cookies(response)


def fetch_one(query, params=()):
    conn = db()
    try:
        stmt, bound = _sql_text(query, params)
        row = conn.execute(stmt, bound).mappings().fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def fetch_all(query, params=()):
    conn = db()
    try:
        stmt, bound = _sql_text(query, params)
        rows = conn.execute(stmt, bound).mappings().fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def execute(query, params=()):
    conn = db()
    try:
        stmt, bound = _sql_text(query, params)
        cur = conn.execute(stmt, bound)
        conn.commit()
        return cur
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def is_glucose_reading_stale(timestamp_str: str, threshold_minutes: int = GLUCOSE_STALE_THRESHOLD_MINUTES) -> bool:
    if not timestamp_str:
        return True
    try:
        reading_time = parse_ts(timestamp_str)
        return (utcnow() - reading_time).total_seconds() / 60 > threshold_minutes
    except (OverflowError, ValueError):
        return True


def freshness_label(timestamp_str: str) -> str:
    try:
        reading_time = parse_ts(timestamp_str)
    except (OverflowError, TypeError, ValueError):
        return "Unknown"
    if is_glucose_reading_stale(timestamp_str):
        age_hours = (utcnow() - reading_time).total_seconds() / 3600
        return "Old" if age_hours > 24 else "Stale"
    age_minutes = (utcnow() - parse_ts(timestamp_str)).total_seconds() / 60
    if age_minutes <= 5:
        return "Live"
    return "Recent"


def contains_suspicious_content(content: str) -> bool:
    patterns = [
        r'\bDROP\b', r'\bSELECT\b', r'\bINSERT\b', r'\bDELETE\b', r'\bUPDATE\b',
        r'\bUNION\b', r'\bSCHEMA\b', r'\bINFORMATION_SCHEMA\b', r'<script>', r'javascript:',
        r'onclick=', r'onload=', r'(--|/\*|\*/)'
    ]
    return any(re.search(p, content or "", re.IGNORECASE) for p in patterns)


def escape_html(unsafe_str: str) -> str:
    return (
        unsafe_str.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


def get_user(user_id: str):
    return fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_username(username: str):
    return fetch_one("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,))


def get_alert_rules(user_id: str):
    rules = fetch_one("SELECT * FROM alert_rules WHERE user_id = ?", (user_id,))
    if not rules:
        now = iso()
        insert_ignore("alert_rules", ["user_id", "updated_at"], (user_id, now), ["user_id"])
        rules = fetch_one("SELECT * FROM alert_rules WHERE user_id = ?", (user_id,))
    return rules


def validate_alert_thresholds(urgent_low: int, low: int, high: int, urgent_high: int):
    if not urgent_low <= low < high <= urgent_high:
        raise ValueError("Alert thresholds must be ordered urgent low <= low < high <= urgent high.")


def validate_target_range(target_low: int, target_high: int):
    if target_low >= target_high:
        raise ValueError("Target low must be below target high.")


def get_notification_settings(user_id: str):
    settings = fetch_one("SELECT * FROM notification_settings WHERE user_id = ?", (user_id,))
    if not settings:
        now = iso()
        insert_ignore("notification_settings", ["user_id", "updated_at"], (user_id, now), ["user_id"])
        settings = fetch_one("SELECT * FROM notification_settings WHERE user_id = ?", (user_id,))
    return settings


def get_emergency_contacts(user_id: str):
    return fetch_all("SELECT * FROM emergency_contacts WHERE user_id = ? ORDER BY created_at ASC", (user_id,))


def save_emergency_contacts(user_id: str, contacts: List[Dict[str, Any]]):
    now = iso()
    conn = db()
    try:
        conn_execute(conn, "DELETE FROM emergency_contacts WHERE user_id = ?", (user_id,))
        for index, contact in enumerate(contacts):
            name = (contact.get("name") or "").strip()
            if not name:
                continue
            conn_execute(conn,
                "INSERT INTO emergency_contacts (id, user_id, name, phone, relationship, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    contact.get("id") or f"ec_{user_id}_{index}_{int(utcnow().timestamp()*1000)}",
                    user_id,
                    name,
                    (contact.get("phone") or "").strip(),
                    (contact.get("relationship") or "").strip(),
                    now,
                    now,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_emergency_contacts(user_id)


def get_shop_catalog():
    return SHOP_CATALOG


def shop_request_payload(row):
    if not row:
        return None
    item = next((entry for entry in SHOP_CATALOG if entry["id"] == row["item_id"]), None)
    return {
        **dict(row),
        "item": item or {
            "id": row["item_id"],
            "name": row["item_name"],
            "price": row["item_price"],
            "category": "Requested",
            "description": "Saved request",
        },
    }


def get_shop_requests(user_id: str):
    rows = fetch_all("SELECT * FROM shop_requests WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    return [shop_request_payload(row) for row in rows]


def save_shop_request(user_id: str, data: dict):
    item_id = data.get("item_id") or ""
    if not isinstance(item_id, str):
        return {"success": False, "message": "item_id must be text."}, 400
    item_id = item_id.strip()
    item = next((entry for entry in SHOP_CATALOG if entry["id"] == item_id), None)
    if not item:
        return {"success": False, "message": "Requested item is not available."}, 400
    existing = fetch_one("SELECT * FROM shop_requests WHERE user_id = ? AND item_id = ?", (user_id, item_id))
    quantity = to_int(data.get("quantity", existing["quantity"] if existing else 1), "quantity", 1, 99)
    notes = clamp_text(data.get("notes", existing["notes"] if existing else ""), "notes", 500)
    now = iso()
    status = clamp_text(data.get("status", existing["status"] if existing else "saved"), "status", 50) or (existing["status"] if existing else "saved")
    if existing:
        execute(
            "UPDATE shop_requests SET quantity = ?, notes = ?, status = ?, updated_at = ? WHERE id = ?",
            (quantity, notes, status, now, existing["id"]),
        )
        request_row = fetch_one("SELECT * FROM shop_requests WHERE id = ?", (existing["id"],))
        return {"success": True, "request": shop_request_payload(request_row)}
    request_id = f"sr_{int(utcnow().timestamp()*1000)}"
    execute(
        "INSERT INTO shop_requests (id, user_id, item_id, item_name, item_price, quantity, notes, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (request_id, user_id, item["id"], item["name"], item["price"], quantity, notes, status, now, now),
    )
    request_row = fetch_one("SELECT * FROM shop_requests WHERE id = ?", (request_id,))
    return {"success": True, "request": shop_request_payload(request_row)}


def get_shop_request_by_id(request_id: str):
    return fetch_one("SELECT * FROM shop_requests WHERE id = ?", (request_id,))


def compute_latest_glucose(user_id: str):
    return fetch_one(
        "SELECT * FROM glucose_readings WHERE user_id = ? AND archived = 0 ORDER BY timestamp DESC LIMIT 1",
        (user_id,),
    )


def get_glucose_analytics(user_id: str, date_range: str = "7D") -> Dict[str, Any]:
    days = {"7D": 7, "14D": 14, "30D": 30, "90D": 90}.get(date_range, 7)
    if date_range == "All Time":
        rows = fetch_all("SELECT * FROM glucose_readings WHERE user_id = ? AND archived = 0 ORDER BY timestamp ASC", (user_id,))
    else:
        cutoff = iso(utcnow() - dt.timedelta(days=days))
        rows = fetch_all(
            "SELECT * FROM glucose_readings WHERE user_id = ? AND archived = 0 AND timestamp >= ? ORDER BY timestamp ASC",
            (user_id, cutoff),
        )
    if not rows:
        return {"average_glucose": 0, "readings_count": 0, "time_in_range_percent": 0, "readings": [], "message": "No glucose readings in the selected date range.", "low_count": 0, "high_count": 0, "stale_data_count": 0, "trend_by_day": []}
    average = round(sum(r["value"] for r in rows) / len(rows), 2)
    in_range = sum(1 for r in rows if 70 <= r["value"] <= 180)
    by_day: Dict[str, List[int]] = {}
    low_count = high_count = stale_count = 0
    for r in rows:
        day = parse_ts(r["timestamp"]).date().isoformat()
        by_day.setdefault(day, []).append(r["value"])
        if r["value"] < 70:
            low_count += 1
        if r["value"] > 180:
            high_count += 1
        if is_glucose_reading_stale(r["timestamp"]):
            stale_count += 1
    trend_by_day = [{"date": k, "average_glucose": round(sum(v) / len(v), 2), "readings": len(v)} for k, v in by_day.items()]
    return {
        "average_glucose": average,
        "readings_count": len(rows),
        "time_in_range_percent": round((in_range / len(rows)) * 100, 2),
        "readings": rows,
        "message": "",
        "low_count": low_count,
        "high_count": high_count,
        "stale_data_count": stale_count,
        "trend_by_day": trend_by_day,
    }


def get_user_achievements(user_id: str) -> List[Dict[str, Any]]:
    rows = fetch_all("SELECT * FROM user_achievements WHERE user_id = ? ORDER BY awarded_at ASC", (user_id,))
    seen = set()
    deduped = []
    for row in rows:
        if row["achievement_id"] not in seen:
            seen.add(row["achievement_id"])
            deduped.append(row)
    return deduped


def get_user_gamification_progress(user_id: str) -> Dict[str, Any]:
    glucose_rows = fetch_all("SELECT * FROM glucose_readings WHERE user_id = ? AND archived = 0 ORDER BY timestamp ASC", (user_id,))
    meals = fetch_all("SELECT * FROM meals WHERE user_id = ? ORDER BY timestamp ASC", (user_id,))
    earned_rows = get_user_achievements(user_id)
    earned = [r["achievement_id"] for r in earned_rows]
    progress = {"streaks": {"glucose_log_streak": 0, "longest_glucose_log_streak": 0}, "meal_counts": {"total_meals_logged": len(meals)}, "achievements_progress": {}, "earned_achievements": earned}
    if glucose_rows:
        dates = sorted({parse_ts(r["timestamp"]).date() for r in glucose_rows})
        streak = longest = 1
        current = dates[0]
        for d in dates[1:]:
            streak = streak + 1 if (d - current).days == 1 else 1
            longest = max(longest, streak)
            current = d
        progress["streaks"]["glucose_log_streak"] = streak if (utcnow().date() in dates or (utcnow().date() - dt.timedelta(days=1)) in dates) else 0
        progress["streaks"]["longest_glucose_log_streak"] = longest
    defs = {
        "first_glucose": ("First Glucose Log", 1),
        "first_meal": ("First Meal Log", 1),
        "three_day": ("3-Day Streak", 3),
        "seven_day": ("7-Day Streak", 7),
        "ten_meals": ("10 Meals", 10),
        "thirty_readings": ("30 Readings", 30),
    }
    if "first_glucose" not in earned and glucose_rows:
        progress["achievements_progress"]["first_glucose"] = {"current": len(glucose_rows), "goal": 1, "description": "Logged your first glucose reading."}
    if "first_meal" not in earned and meals:
        progress["achievements_progress"]["first_meal"] = {"current": len(meals), "goal": 1, "description": "Logged your first meal."}
    if "three_day" not in earned:
        progress["achievements_progress"]["three_day"] = {"current": progress["streaks"]["glucose_log_streak"], "goal": 3, "description": "Logged glucose for 3 consecutive days."}
    if "seven_day" not in earned:
        progress["achievements_progress"]["seven_day"] = {"current": progress["streaks"]["glucose_log_streak"], "goal": 7, "description": "Logged glucose for 7 consecutive days."}
    if "ten_meals" not in earned:
        progress["achievements_progress"]["ten_meals"] = {"current": len(meals), "goal": 10, "description": "Logged 10 meals."}
    if "thirty_readings" not in earned:
        progress["achievements_progress"]["thirty_readings"] = {"current": len(glucose_rows), "goal": 30, "description": "Logged 30 glucose readings."}
    return progress


def award_achievement(user_id: str, achievement_id: str):
    try:
        execute("INSERT INTO user_achievements (user_id, achievement_id, awarded_at) VALUES (?, ?, ?)", (user_id, achievement_id, iso()))
        return {"success": True}
    except IntegrityError:
        return {"success": False, "message": "Achievement already awarded"}


def create_meal(data: dict, user_id: str):
    meal_id = clamp_text(data.get("id", ""), "id", 120) or f"m{uuid.uuid4().hex}"
    name = clamp_text(data.get("name"), "name", 120) or "Meal"
    carbs = to_float(data.get("carbs", 0), "carbs", 0)
    protein = to_float(data.get("protein", 0), "protein", 0)
    fat = to_float(data.get("fat", 0), "fat", 0)
    calories = to_float(data.get("calories", 0), "calories", 0)
    notes = clamp_text(data.get("notes", ""), "notes", 500)
    photo_url = clamp_text(data.get("photo_url", ""), "photo_url", 500)
    timestamp = normalize_timestamp(data.get("timestamp"))
    execute(
        "INSERT INTO meals (id, user_id, name, carbs, protein, fat, calories, timestamp, notes, photo_url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (meal_id, user_id, name, carbs, protein, fat, calories, timestamp, notes, photo_url, iso()),
    )
    meal_count = fetch_one("SELECT COUNT(*) AS count FROM meals WHERE user_id = ?", (user_id,))["count"]
    award_achievement(user_id, "first_meal")
    if meal_count >= 10:
        award_achievement(user_id, "ten_meals")
    return fetch_one("SELECT * FROM meals WHERE id = ?", (meal_id,))


def create_glucose(data: dict, user_id: str):
    rid = clamp_text(data.get("id", ""), "id", 120) or f"g{uuid.uuid4().hex}"
    ts = normalize_timestamp(data.get("timestamp"))
    value = to_int(data.get("value"), "value", 20, 600)
    source = clamp_text(data.get("source", "manual"), "source", 40) or "manual"
    notes = clamp_text(data.get("notes", ""), "notes", 500)
    symptoms = clamp_text(data.get("symptoms", ""), "symptoms", 250)
    context = clamp_text(data.get("context", ""), "context", 250)
    execute(
        "INSERT INTO glucose_readings (id, user_id, value, timestamp, source, notes, symptoms, context, is_stale, archived, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, user_id, value, ts, source, notes, symptoms, context, int(is_glucose_reading_stale(ts)), 0, iso()),
    )
    reading_count = fetch_one("SELECT COUNT(*) AS count FROM glucose_readings WHERE user_id = ? AND archived = 0", (user_id,))["count"]
    award_achievement(user_id, "first_glucose")
    if reading_count >= 30:
        award_achievement(user_id, "thirty_readings")
    return fetch_one("SELECT * FROM glucose_readings WHERE id = ?", (rid,))


def create_insulin(data: dict, user_id: str):
    iid = clamp_text(data.get("id", ""), "id", 120) or f"i{uuid.uuid4().hex}"
    insulin_type = clamp_text(data.get("insulin_type", "bolus"), "insulin_type", 40) or "bolus"
    units = to_float(data.get("units"), "units", 0)
    notes = clamp_text(data.get("notes", ""), "notes", 500)
    linked_meal_id = clamp_text(data.get("linked_meal_id", ""), "linked_meal_id", 120)
    if linked_meal_id and not fetch_one("SELECT id FROM meals WHERE id = ? AND user_id = ?", (linked_meal_id, user_id)):
        raise ValueError("linked_meal_id must reference one of your meals.")
    timestamp = normalize_timestamp(data.get("timestamp"))
    execute("INSERT INTO insulin_logs (id, user_id, insulin_type, units, timestamp, notes, linked_meal_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (iid, user_id, insulin_type, units, timestamp, notes, linked_meal_id, iso()))
    return fetch_one("SELECT * FROM insulin_logs WHERE id = ?", (iid,))


def model_alert_for_reading(reading, rules):
    if not reading:
        return None
    stale = is_glucose_reading_stale(reading["timestamp"], rules["stale_minutes"])
    if stale:
        return {"triggered": False, "reason": "stale", "label": freshness_label(reading["timestamp"]), "source_timestamp": reading["timestamp"]}
    value = reading["value"]
    if value <= rules["urgent_low"]:
        return {"triggered": True, "severity": "urgent_low", "reason": "urgent low glucose", "source_timestamp": reading["timestamp"], "value": value}
    if value < rules["low"]:
        return {"triggered": True, "severity": "low", "reason": "low glucose", "source_timestamp": reading["timestamp"], "value": value}
    if value >= rules["urgent_high"]:
        return {"triggered": True, "severity": "urgent_high", "reason": "urgent high glucose", "source_timestamp": reading["timestamp"], "value": value}
    if value > rules["high"]:
        return {"triggered": True, "severity": "high", "reason": "high glucose", "source_timestamp": reading["timestamp"], "value": value}
    return {"triggered": False, "reason": "in_range", "source_timestamp": reading["timestamp"], "value": value}


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "request_id": getattr(g, "request_id", None)})


@app.route("/api/ready", methods=["GET"])
def ready():
    conn = None
    try:
        conn = db()
        conn.exec_driver_sql("SELECT 1")
    except Exception:
        return jsonify({"ok": False, "message": "Database unavailable.", "request_id": getattr(g, "request_id", None)}), 503
    finally:
        if conn is not None:
            conn.close()
    return jsonify({"ok": True, "request_id": getattr(g, "request_id", None)})


@app.route("/api/profile/<user_id>", methods=["GET", "PUT"])
def profile(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    user = get_user(user_id)
    if not user:
        return api_error("User not found.", 404, "NOT_FOUND")
    if request.method == "GET":
        return jsonify(sanitize_user(user) or {"message": "User not found"}), (200 if user else 404)
    data, error = parse_json_body()
    if error:
        return error
    try:
        settings = data.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError("settings must be an object.")
        target_low = to_int(data.get("target_low", user["target_low"]), "target_low", 40, 250)
        target_high = to_int(data.get("target_high", user["target_high"]), "target_high", 50, 350)
        validate_target_range(target_low, target_high)
        settings_json = json.dumps(settings) if "settings" in data else user["settings_json"]
        execute(
            "UPDATE users SET username = ?, diabetes_type = ?, units = ?, target_low = ?, target_high = ?, settings_json = ?, updated_at = ? WHERE id = ?",
            (
                clamp_text(data.get("username", user["username"]), "username", 80) or user["username"],
                clamp_text(data.get("diabetes_type", user["diabetes_type"]), "diabetes_type", 80) or user["diabetes_type"],
                clamp_text(data.get("units", user["units"]), "units", 20) or user["units"],
                target_low,
                target_high,
                settings_json,
                iso(),
                user_id,
            ),
        )
    except IntegrityError:
        return api_error("Username already exists.", 409, "CONFLICT")
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    return jsonify({"success": True, "profile": sanitize_user(get_user(user_id))})


@app.route("/api/glucose/latest/<user_id>", methods=["GET"])
def get_latest_glucose(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    latest = compute_latest_glucose(user_id)
    if not latest:
        return jsonify({"message": "No glucose readings found."}), 404
    latest["is_stale"] = int(is_glucose_reading_stale(latest["timestamp"]))
    latest["freshness_label"] = freshness_label(latest["timestamp"])
    return jsonify(latest)


@app.route("/api/glucose/<user_id>", methods=["GET", "POST"])
def glucose_collection(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    if request.method == "GET":
        rows = fetch_all("SELECT * FROM glucose_readings WHERE user_id = ? AND archived = 0 ORDER BY timestamp DESC", (user_id,))
        for row in rows:
            row["is_stale"] = int(is_glucose_reading_stale(row["timestamp"]))
            row["freshness_label"] = freshness_label(row["timestamp"])
        return jsonify(rows)
    body, error = parse_json_body()
    if error:
        return error
    try:
        reading = create_glucose(body, user_id)
    except IntegrityError:
        return api_error("Glucose reading already exists.", 409, "CONFLICT")
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "reading": reading}), 201


@app.route("/api/glucose/<reading_id>", methods=["DELETE"])
def delete_glucose_reading(reading_id):
    _, _, auth_error = require_record_owner("glucose_readings", reading_id)
    if auth_error:
        return auth_error
    execute("UPDATE glucose_readings SET archived = 1 WHERE id = ?", (reading_id,))
    return jsonify({"success": True, "message": "Glucose reading archived."})


@app.route("/api/meals/<user_id>", methods=["GET", "POST"])
def meals(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return jsonify(fetch_all("SELECT * FROM meals WHERE user_id = ? ORDER BY timestamp DESC", (user_id,)))
    body, error = parse_json_body()
    if error:
        return error
    try:
        meal = create_meal(body, user_id)
    except IntegrityError:
        return api_error("Meal already exists.", 409, "CONFLICT")
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "meal": meal}), 201


@app.route("/api/meals/<meal_id>", methods=["PUT", "DELETE"])
def meal_item(meal_id):
    _, meal, auth_error = require_record_owner("meals", meal_id)
    if auth_error:
        return auth_error
    if request.method == "DELETE":
        execute("DELETE FROM meals WHERE id = ?", (meal_id,))
        return jsonify({"success": True})
    body, error = parse_json_body()
    if error:
        return error
    try:
        timestamp = normalize_timestamp(body.get("timestamp"), meal["timestamp"])
        execute(
            "UPDATE meals SET name = ?, carbs = ?, protein = ?, fat = ?, calories = ?, timestamp = ?, notes = ?, photo_url = ? WHERE id = ?",
            (
                clamp_text(body.get("name", meal["name"]), "name", 120) or "Meal",
                to_float(body.get("carbs", meal["carbs"]), "carbs", 0),
                to_float(body.get("protein", meal["protein"]), "protein", 0),
                to_float(body.get("fat", meal["fat"]), "fat", 0),
                to_float(body.get("calories", meal["calories"]), "calories", 0),
                timestamp,
                clamp_text(body.get("notes", meal["notes"]), "notes", 500),
                clamp_text(body.get("photo_url", meal["photo_url"]), "photo_url", 500),
                meal_id,
            ),
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "meal": fetch_one("SELECT * FROM meals WHERE id = ?", (meal_id,))})


@app.route("/api/insulin/<user_id>", methods=["GET", "POST"])
def insulin(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return jsonify(fetch_all("SELECT * FROM insulin_logs WHERE user_id = ? ORDER BY timestamp DESC", (user_id,)))
    body, error = parse_json_body()
    if error:
        return error
    try:
        log = create_insulin(body, user_id)
    except IntegrityError:
        return api_error("Insulin log already exists.", 409, "CONFLICT")
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "insulin": log}), 201


@app.route("/api/alerts/<user_id>", methods=["GET"])
def alerts(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    rules = get_alert_rules(user_id)
    latest = compute_latest_glucose(user_id)
    return jsonify({"rules": rules, "latest_alert": model_alert_for_reading(latest, rules)})


@app.route("/api/alert-rules/<user_id>", methods=["GET", "PUT"])
def alert_rules(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return jsonify(get_alert_rules(user_id))
    current_rules = get_alert_rules(user_id)
    body, error = parse_json_body()
    if error:
        return error
    try:
        urgent_low = to_int(body.get("urgent_low", current_rules["urgent_low"]), "urgent_low", 40, 120)
        low = to_int(body.get("low", current_rules["low"]), "low", 40, 150)
        high = to_int(body.get("high", current_rules["high"]), "high", 90, 350)
        urgent_high = to_int(body.get("urgent_high", current_rules["urgent_high"]), "urgent_high", 120, 500)
        stale_minutes = to_int(body.get("stale_minutes", current_rules["stale_minutes"]), "stale_minutes", 5, 1440)
        missed_meal_hours = to_int(body.get("missed_meal_hours", current_rules["missed_meal_hours"]), "missed_meal_hours", 1, 48)
        validate_alert_thresholds(urgent_low, low, high, urgent_high)
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    execute(
        "UPDATE alert_rules SET urgent_low = ?, low = ?, high = ?, urgent_high = ?, stale_minutes = ?, missed_meal_hours = ?, updated_at = ? WHERE user_id = ?",
        (
            urgent_low,
            low,
            high,
            urgent_high,
            stale_minutes,
            missed_meal_hours,
            iso(),
            user_id,
        ),
    )
    return jsonify({"success": True, "alert_rules": get_alert_rules(user_id)})


profane_words = ["badword1", "badword2"]


def get_community_posts(is_admin: bool = False) -> List[Dict[str, Any]]:
    rows = fetch_all("SELECT * FROM community_posts ORDER BY posted_at DESC")
    out = []
    for post in rows:
        if is_admin or post["status"] == "active":
            user = get_user(post["user_id"]) or {"username": "Unknown User"}
            out.append({**post, "username": user["username"], "display_content": escape_html(post["content"])})
    return out


def create_community_post(user_id: str, content: str):
    content = clamp_text(content, "content", 1000)
    if not content:
        raise ValueError("content is required.")
    if contains_suspicious_content(content):
        return {"success": False, "message": "Post contains suspicious content and cannot be published."}
    pid = f"c{uuid.uuid4().hex}"
    execute("INSERT INTO community_posts (id, user_id, content, status, posted_at) VALUES (?, ?, ?, 'active', ?)", (pid, user_id, content, iso()))
    return {"success": True, "post": fetch_one("SELECT * FROM community_posts WHERE id = ?", (pid,))}


def hide_community_post(post_id: str, moderator_id: str):
    execute("UPDATE community_posts SET status = 'hidden', moderated_by = ?, moderated_at = ? WHERE id = ?", (moderator_id, iso(), post_id))
    return {"success": True, "message": "Post hidden successfully."}


def delete_community_post(post_id: str):
    execute("DELETE FROM community_posts WHERE id = ?", (post_id,))
    return {"success": True, "message": "Post deleted successfully."}


community_bp = Blueprint("community", __name__)


@community_bp.route("/posts", methods=["GET"])
def community_posts_route():
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    return jsonify(get_community_posts(is_admin_user(current_user)))


@community_bp.route("/posts", methods=["POST"])
def community_create_route():
    limited = check_rate_limit("community_create", 20)
    if limited:
        return limited
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    data, error = parse_json_body()
    if error:
        return error
    try:
        result = create_community_post(current_user["id"], data.get("content", ""))
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    return jsonify(result), (201 if result["success"] else 400)


@community_bp.route("/posts/<post_id>/hide", methods=["POST"])
def community_hide_route(post_id):
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    if not is_admin_user(current_user):
        return api_error("Moderator access is required.", 403, "FORBIDDEN")
    if not fetch_one("SELECT id FROM community_posts WHERE id = ?", (post_id,)):
        return api_error("Community post not found.", 404, "NOT_FOUND")
    return jsonify(hide_community_post(post_id, current_user["id"]))


@community_bp.route("/posts/<post_id>", methods=["DELETE"])
def community_delete_route(post_id):
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    if not is_admin_user(current_user):
        return api_error("Moderator access is required.", 403, "FORBIDDEN")
    if not fetch_one("SELECT id FROM community_posts WHERE id = ?", (post_id,)):
        return api_error("Community post not found.", 404, "NOT_FOUND")
    return jsonify(delete_community_post(post_id))


@community_bp.route("/posts/<post_id>/report", methods=["POST"])
def community_report_route(post_id):
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    data, error = parse_json_body(required=False)
    if error:
        return error
    if not fetch_one("SELECT id FROM community_posts WHERE id = ?", (post_id,)):
        return api_error("Community post not found.", 404, "NOT_FOUND")
    try:
        reason = clamp_text(data.get("reason", "Reported by user"), "reason", 500)
        execute(
            "INSERT INTO community_reports (id, post_id, reporter_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (f"r{uuid.uuid4().hex}", post_id, current_user["id"], reason, iso()),
        )
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    return jsonify({"success": True, "message": "Report saved for moderation."})


app.register_blueprint(community_bp, url_prefix="/api/community")


@app.route("/api/achievements/<user_id>", methods=["GET"])
def achievements_route(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    return jsonify(get_user_achievements(user_id))


@app.route("/api/achievements/progress/<user_id>", methods=["GET"])
def achievements_progress_route(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    progress = get_user_gamification_progress(user_id)
    progress["earned_achievements"] = sorted(progress["earned_achievements"])
    return jsonify(progress)


@app.route("/api/achievements/award", methods=["POST"])
def award_route():
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    body, error = parse_json_body()
    if error:
        return error
    try:
        target_user_id = clamp_text(body.get("user_id", ""), "user_id", 120)
        achievement_id = clamp_text(body.get("achievement_id", ""), "achievement_id", 80)
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    if not target_user_id or not achievement_id:
        return api_error("user_id and achievement_id are required.", 400, "VALIDATION_ERROR")
    if target_user_id != current_user["id"] and not is_admin_user(current_user):
        return api_error("You do not have access to this user's data.", 403, "FORBIDDEN")
    if not get_user(target_user_id):
        return api_error("User not found.", 404, "NOT_FOUND")
    if not fetch_one("SELECT id FROM achievements WHERE id = ?", (achievement_id,)):
        return api_error("Achievement not found.", 404, "NOT_FOUND")
    result = award_achievement(target_user_id, achievement_id)
    return jsonify(result), (200 if result["success"] else 409)


@app.route("/api/analytics/glucose/<user_id>", methods=["GET"])
def analytics_route(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    return jsonify(get_glucose_analytics(user_id, request.args.get("date_range", "7D")))


cgm_bp = Blueprint("cgm", __name__)


@cgm_bp.route("/status", methods=["GET"])
def cgm_status():
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    user_id = current_user["id"]
    connection = fetch_one("SELECT * FROM cgm_connections WHERE user_id = ?", (user_id,)) or {}
    available = False
    return jsonify({
        "state": connection.get("state", "not_connected"),
        "dexcom_cgm_available": available,
        "backend_upgrade_needed": not available,
        "message": "Dexcom CGM is not connected in this beta. Add production credentials and enable the integration before use.",
    })


@cgm_bp.route("/sync", methods=["POST"])
def cgm_sync():
    _, auth_error = require_current_user()
    if auth_error:
        return auth_error
    return api_error("Dexcom CGM sync is not enabled for this beta environment.", 503, "INTEGRATION_DISABLED")


@cgm_bp.route("/verify-auth", methods=["GET"])
def cgm_verify():
    _, auth_error = require_current_user()
    if auth_error:
        return auth_error
    return api_error("Dexcom CGM verification is not enabled for this beta environment.", 503, "INTEGRATION_DISABLED")


@cgm_bp.route("/demo-sync", methods=["POST"])
def cgm_demo_sync():
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    if CONFIG.is_production:
        return api_error("Demo CGM sync is disabled in production.", 403, "FORBIDDEN")
    user_id = current_user["id"]
    now = iso()
    execute(
        "INSERT INTO cgm_connections (user_id, state, backend_available, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET state = excluded.state, backend_available = excluded.backend_available, updated_at = excluded.updated_at",
        (user_id, "demo_mode", 0, now),
    )
    return jsonify({"success": True, "message": "Demo CGM sync saved locally.", "state": "demo_mode"})


app.register_blueprint(cgm_bp, url_prefix="/api/cgm")


notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/test-low-email", methods=["POST"])
def test_low_email():
    _, auth_error = require_current_user()
    if auth_error:
        return auth_error
    return api_error("Email notifications are not enabled for this beta environment.", 503, "INTEGRATION_DISABLED")


app.register_blueprint(notifications_bp, url_prefix="/api/notifications")


def create_app():
    return app


@app.route("/api/settings/<user_id>", methods=["GET", "PUT"])
def settings_route(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    user = get_user(user_id)
    if not user:
        return api_error("User not found.", 404, "NOT_FOUND")
    if request.method == "GET":
        settings = get_notification_settings(user_id)
        rules = get_alert_rules(user_id)
        return jsonify({"profile": sanitize_user(user), "alert_rules": rules, "notification_settings": settings})
    current_alert_rules = get_alert_rules(user_id)
    current_notification_settings = get_notification_settings(user_id)
    body, error = parse_json_body()
    if error:
        return error
    profile = body.get("profile", {})
    rules = body.get("alert_rules", {})
    notification_settings = body.get("notification_settings", {})
    if any(not isinstance(section, dict) for section in (profile, rules, notification_settings)):
        return api_error("profile, alert_rules, and notification_settings must be objects.", 400, "VALIDATION_ERROR")
    try:
        target_low = to_int(profile.get("target_low", user["target_low"]), "target_low", 40, 250)
        target_high = to_int(profile.get("target_high", user["target_high"]), "target_high", 50, 350)
        validate_target_range(target_low, target_high)
        urgent_low = to_int(rules.get("urgent_low", current_alert_rules["urgent_low"]), "urgent_low", 40, 120)
        low = to_int(rules.get("low", current_alert_rules["low"]), "low", 40, 150)
        high = to_int(rules.get("high", current_alert_rules["high"]), "high", 90, 350)
        urgent_high = to_int(rules.get("urgent_high", current_alert_rules["urgent_high"]), "urgent_high", 120, 500)
        validate_alert_thresholds(urgent_low, low, high, urgent_high)
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    try:
        username = clamp_text(profile.get("username", user["username"]), "username", 80) or user["username"]
        diabetes_type = clamp_text(profile.get("diabetes_type", user["diabetes_type"]), "diabetes_type", 80) or user["diabetes_type"]
        units = clamp_text(profile.get("units", user["units"]), "units", 20) or user["units"]
        stale_minutes = to_int(rules.get("stale_minutes", current_alert_rules["stale_minutes"]), "stale_minutes", 5, 1440)
        missed_meal_hours = to_int(rules.get("missed_meal_hours", current_alert_rules["missed_meal_hours"]), "missed_meal_hours", 1, 48)
        notification_values = (
            int(to_bool(notification_settings.get("low_glucose_alert"), "low_glucose_alert", bool(current_notification_settings["low_glucose_alert"]))),
            int(to_bool(notification_settings.get("high_glucose_alert"), "high_glucose_alert", bool(current_notification_settings["high_glucose_alert"]))),
            int(to_bool(notification_settings.get("stale_data_alert"), "stale_data_alert", bool(current_notification_settings["stale_data_alert"]))),
            int(to_bool(notification_settings.get("missed_meal_alert"), "missed_meal_alert", bool(current_notification_settings["missed_meal_alert"]))),
            int(to_bool(notification_settings.get("email_enabled"), "email_enabled", bool(current_notification_settings["email_enabled"]))),
            int(to_bool(notification_settings.get("sms_enabled"), "sms_enabled", bool(current_notification_settings["sms_enabled"]))),
            int(to_bool(notification_settings.get("push_enabled"), "push_enabled", bool(current_notification_settings["push_enabled"]))),
        )
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    now = iso()
    conn = db()
    try:
        conn_execute(conn,
            "UPDATE users SET username = ?, diabetes_type = ?, units = ?, target_low = ?, target_high = ?, updated_at = ? WHERE id = ?",
            (
                username,
                diabetes_type,
                units,
                target_low,
                target_high,
                now,
                user_id,
            ),
        )
        conn_execute(conn,
            "UPDATE alert_rules SET urgent_low = ?, low = ?, high = ?, urgent_high = ?, stale_minutes = ?, missed_meal_hours = ?, updated_at = ? WHERE user_id = ?",
            (
                urgent_low,
                low,
                high,
                urgent_high,
                stale_minutes,
                missed_meal_hours,
                now,
                user_id,
            ),
        )
        conn_execute(conn,
            "UPDATE notification_settings SET low_glucose_alert = ?, high_glucose_alert = ?, stale_data_alert = ?, missed_meal_alert = ?, email_enabled = ?, sms_enabled = ?, push_enabled = ?, updated_at = ? WHERE user_id = ?",
            (
                *notification_values,
                now,
                user_id,
            ),
        )
        conn.commit()
    except IntegrityError:
        conn.rollback()
        return api_error("Username already exists.", 409, "CONFLICT")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return jsonify({"success": True, "settings": {"profile": sanitize_user(get_user(user_id)), "alert_rules": get_alert_rules(user_id), "notification_settings": get_notification_settings(user_id)}})


@app.route("/api/coach/respond", methods=["POST"])
def coach_respond():
    current_user, auth_error = require_current_user()
    if auth_error:
        return auth_error
    body, error = parse_json_body()
    if error:
        return error
    try:
        prompt = (clamp_text(body.get("message", ""), "message", 2000) or "").lower()
        requested_user = clamp_text(body.get("user_id", ""), "user_id", 120) or current_user["id"]
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    if not prompt:
        return api_error("message is required.", 400, "VALIDATION_ERROR")
    if requested_user != current_user["id"] and not is_admin_user(current_user):
        return api_error("You do not have access to this user's data.", 403, "FORBIDDEN")
    latest = compute_latest_glucose(requested_user)
    meals = fetch_all("SELECT * FROM meals WHERE user_id = ? ORDER BY timestamp DESC LIMIT 3", (requested_user,))
    insulin_logs = fetch_all("SELECT * FROM insulin_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT 3", (requested_user,))
    if any(term in prompt for term in ["dose", "dosage", "insulin units", "how much insulin"]):
        return jsonify({"success": False, "message": "I can’t help with insulin dosing. Please contact your clinician."}), 400
    safety_concern = bool(latest and (latest["value"] < 54 or latest["value"] > 300 or is_glucose_reading_stale(latest["timestamp"])))
    model = CONFIG.nvidia_safety_model if safety_concern else CONFIG.nvidia_coach_model
    system_prompt = (
        "You are a safety-first diabetes coach. "
        "Never recommend insulin dosing. "
        "Return a concise reply and exactly five next steps as numbered lines."
    )
    context_lines = []
    if latest:
        context_lines.append(f"Latest glucose: {latest['value']} mg/dL at {latest['timestamp']}.")
    if meals:
        context_lines.append(f"Most recent meal: {meals[0]['name']} with {meals[0]['carbs']}g carbs at {meals[0]['timestamp']}.")
    if insulin_logs:
        context_lines.append(f"Most recent insulin log: {insulin_logs[0]['units']}u at {insulin_logs[0]['timestamp']}.")
    if safety_concern:
        context_lines.append("Safety concern detected from the latest reading.")
    user_prompt = "\n".join([
        f"User request: {body.get('message') or ''}",
        *context_lines,
    ])
    fallback_reply = "Your logs suggest a safety concern. Please open emergency guidance and consider contacting your care team." if safety_concern else "I can help summarize patterns, suggest questions for your doctor, and reflect on your logs."
    fallback_next_top_5 = [
        "Open Emergency Guidance now." if safety_concern else "Review your most recent glucose trend for patterns.",
        "Recheck glucose if you have a safe, approved way to do so." if safety_concern else ("Check your latest meals and insulin logs for timing mismatches." if not meals else f"Review the last meal: {meals[0]['name']} ({meals[0]['carbs']}g carbs)."),
        "Contact your care team about the out-of-range or stale reading." if safety_concern else ("Bring one clear question to your next clinician visit." if not insulin_logs else f"Review the last insulin log: {insulin_logs[0]['units']}u at {insulin_logs[0]['timestamp']}."),
        "Keep your emergency contacts current." if safety_concern else "Log your next reading or meal consistently.",
        "Use Emergency Guidance for urgent symptoms." if safety_concern else "Share notable patterns with your care team.",
    ]
    try:
        reply = nvidia_chat_completion(model, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        next_top_5 = extract_next_top_5(reply)
        if len(next_top_5) < 5 and not safety_concern:
            raise RuntimeError("No coach steps returned.")
        if len(next_top_5) < 5:
            next_top_5 = (next_top_5 + fallback_next_top_5)[:5]
        first_line, *rest = reply.splitlines()
        clean_reply = first_line.strip()
        if not clean_reply:
            raise RuntimeError("No coach reply returned.")
        return jsonify({"success": True, "reply": clean_reply, "next_top_5": next_top_5})
    except Exception:
        return jsonify({"success": True, "reply": fallback_reply, "next_top_5": fallback_next_top_5})


@app.route("/api/meals/<user_id>/summary", methods=["GET"])
def meal_summary(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    meals = fetch_all("SELECT * FROM meals WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    return jsonify({"count": len(meals), "average_carbs": round(sum(float(m["carbs"]) for m in meals) / len(meals), 2) if meals else 0, "meals": meals})


@app.route("/api/insulin/<user_id>/summary", methods=["GET"])
def insulin_summary(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    logs = fetch_all("SELECT * FROM insulin_logs WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    return jsonify({"count": len(logs), "logs": logs})


@app.route("/api/alerts/evaluate/<user_id>", methods=["GET"])
def evaluate_alerts(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    rules = get_alert_rules(user_id)
    latest = compute_latest_glucose(user_id)
    alert = model_alert_for_reading(latest, rules)
    return jsonify({"alert": alert, "rules": rules, "latest": latest})


@app.route("/api/emergency/guidance", methods=["GET"])
def emergency_guidance():
    return jsonify({
        "disclaimer": "This is not a substitute for emergency care.",
        "protocols": [
            "If unconscious, having a seizure, or unable to swallow, call emergency services immediately.",
            "If severe low or high symptoms persist, contact your care team or emergency services.",
        ],
        "contacts": [],
    })


@app.route("/api/emergency/contacts/<user_id>", methods=["GET", "PUT"])
def emergency_contacts_route(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return jsonify(get_emergency_contacts(user_id))
    body, error = parse_json_body(required=False)
    if error:
        return error
    contacts = body.get("contacts", [])
    if not isinstance(contacts, list) or any(not isinstance(contact, dict) for contact in contacts):
        return api_error("contacts must be a list of objects.", 400, "VALIDATION_ERROR")
    try:
        validated_contacts = []
        contact_ids = set()
        for contact in contacts:
            name = clamp_text(contact.get("name", ""), "name", 120) or ""
            phone = clamp_text(contact.get("phone", ""), "phone", 40) or ""
            contact_id = clamp_text(contact.get("id", ""), "id", 120) or ""
            if contact_id and contact_id in contact_ids:
                raise ValueError("Emergency contact IDs must be unique.")
            contact_ids.add(contact_id)
            if bool(name.strip()) != bool(phone.strip()):
                return api_error("Each emergency contact needs both a name and phone number.", 400, "VALIDATION_ERROR")
            validated_contacts.append({
                "id": contact_id,
                "name": name,
                "phone": phone,
                "relationship": clamp_text(contact.get("relationship", ""), "relationship", 80) or "",
            })
    except ValueError as exc:
        return api_error(str(exc), 400, "VALIDATION_ERROR")
    return jsonify({"success": True, "contacts": save_emergency_contacts(user_id, validated_contacts)})


@app.route("/api/shop/catalog", methods=["GET"])
def shop_catalog_route():
    return jsonify(get_shop_catalog())


@app.route("/api/shop/requests/<user_id>", methods=["GET", "POST"])
def shop_requests_route(user_id):
    _, auth_error = require_route_user(user_id)
    if auth_error:
        return auth_error
    if request.method == "GET":
        return jsonify(get_shop_requests(user_id))
    body, error = parse_json_body(required=False)
    if error:
        return error
    try:
        result = save_shop_request(user_id, body)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if isinstance(result, tuple):
        payload, status_code = result
    else:
        payload, status_code = result, 200
    return jsonify(payload), status_code


@app.route("/api/shop/request/<request_id>", methods=["PUT", "DELETE"])
def shop_request_item_route(request_id):
    _, request_row, auth_error = require_record_owner("shop_requests", request_id)
    if auth_error:
        return auth_error
    if request.method == "DELETE":
        execute("DELETE FROM shop_requests WHERE id = ?", (request_id,))
        return jsonify({"success": True, "message": "Saved request removed."})
    body, error = parse_json_body(required=False)
    if error:
        return error
    try:
        quantity = to_int(body.get("quantity", request_row["quantity"]), "quantity", 1, 99)
        notes = clamp_text(body.get("notes", request_row["notes"]), "notes", 500)
        status = clamp_text(body.get("status", request_row["status"]), "status", 50) or request_row["status"]
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    execute(
        "UPDATE shop_requests SET quantity = ?, notes = ?, status = ?, updated_at = ? WHERE id = ?",
        (
            quantity,
            notes,
            status,
            iso(),
            request_id,
        ),
    )
    return jsonify({"success": True, "request": shop_request_payload(get_shop_request_by_id(request_id))})


@app.route("/api/demo/reset", methods=["POST"])
def reset_demo():
    if not CONFIG.demo_reset_enabled:
        return jsonify({"success": False, "message": "Demo reset is disabled in production."}), 403
    if request.remote_addr not in {"127.0.0.1", "::1"}:
        return jsonify({"success": False, "message": "Demo reset is only available locally."}), 403
    conn = db()
    try:
        for table in [
            "glucose_readings",
            "meals",
            "insulin_logs",
            "user_achievements",
            "achievements",
            "community_posts",
            "community_reports",
            "cgm_connections",
            "alert_rules",
            "notification_settings",
            "emergency_contacts",
            "shop_requests",
            "sessions",
            "users",
        ]:
            conn.exec_driver_sql(f"DELETE FROM {table}")
        seed_demo_data(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return jsonify({"success": True})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def frontend_app(path):
    if path.startswith("api/"):
        abort(404)
    if path and (FRONTEND_BUILD_DIR / path).exists():
        return send_from_directory(FRONTEND_BUILD_DIR, path)
    if (FRONTEND_BUILD_DIR / "index.html").exists():
        return send_from_directory(FRONTEND_BUILD_DIR, "index.html")
    return jsonify({"success": False, "message": "Frontend build not found."}), 404


if __name__ == "__main__":
    log_event("info", "application_starting", port=CONFIG.port, app_env=CONFIG.app_env)
    app.run(debug=CONFIG.flask_debug, port=CONFIG.port)
