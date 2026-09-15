from __future__ import annotations

import base64
import json
import hashlib
import hmac
import io
import os
import secrets
import smtplib
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from email.message import EmailMessage
from urllib.parse import quote, unquote, urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet, InvalidToken
from PIL import Image, ImageOps, UnidentifiedImageError

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "classificaja.db"
UPLOAD_DIR = BASE_DIR / "uploads"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgresql://", "postgres://"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = (os.getenv("SUPABASE_SECRET_KEY") or "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "product-images").strip() or "product-images"
USE_SUPABASE_STORAGE = bool(SUPABASE_URL and SUPABASE_SECRET_KEY)
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "false" if USE_POSTGRES else "true").lower() in {"1", "true", "yes", "sim"}
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

# V2.18: payment credentials use a dedicated key. Never derive this key from
# unrelated production secrets, because rotating an admin password or Supabase key
# must not make encrypted payment credentials unreadable.
PAYMENT_CONFIG_SECRET = (os.getenv("PAYMENT_CONFIG_KEY") or "").strip()
LEGACY_PAYMENT_CONFIG_SECRET = "|".join(x for x in [SUPABASE_SECRET_KEY, os.getenv("ADMIN_PASSWORD", "").strip()] if x)

ACCOUNT_TOKEN_SECRET = (os.getenv("ACCOUNT_TOKEN_SECRET") or PAYMENT_CONFIG_SECRET or SUPABASE_SECRET_KEY or os.getenv("ADMIN_PASSWORD", "")).strip()
FRONTEND_URL = (os.getenv("FRONTEND_URL") or PUBLIC_BASE_URL or "http://localhost:5173").strip().rstrip("/")
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "sim"}
REQUIRE_EMAIL_VERIFICATION_FOR_FREE = os.getenv("REQUIRE_EMAIL_VERIFICATION_FOR_FREE", "true" if USE_POSTGRES else "false").lower() in {"1", "true", "yes", "sim"}
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in {"1", "true", "yes", "sim"}
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "true" if USE_POSTGRES else "false").lower() in {"1", "true", "yes", "sim"}

PAYMENT_PROVIDER_DEFS = {
    "mercadopago": {
        "label": "Mercado Pago",
        "description": "Recebimento via PIX usando credenciais da sua aplicação Mercado Pago.",
        "fields": [
            {"key": "public_key", "label": "Public Key", "secret": False},
            {"key": "access_token", "label": "Access Token", "secret": True},
        ],
        "required": ["access_token"],
    },
    "asaas": {
        "label": "Asaas",
        "description": "PIX com API Key da sua conta Asaas.",
        "fields": [
            {"key": "api_key", "label": "API Key", "secret": True},
        ],
        "required": ["api_key"],
    },
    "pagbank": {
        "label": "PagBank",
        "description": "Recebimento via PIX com token da sua integração PagBank.",
        "fields": [
            {"key": "token", "label": "Token", "secret": True},
            {"key": "client_id", "label": "Client ID (quando exigido)", "secret": True},
            {"key": "client_secret", "label": "Client Secret (quando exigido)", "secret": True},
        ],
        "required": ["token"],
    },
    "efipay": {
        "label": "Efí Bank",
        "description": "Integração PIX da Efí com Client ID e Client Secret.",
        "fields": [
            {"key": "client_id", "label": "Client ID", "secret": True},
            {"key": "client_secret", "label": "Client Secret", "secret": True},
            {"key": "pix_key", "label": "Chave PIX", "secret": True},
        ],
        "required": ["client_id", "client_secret"],
    },
    "inter": {
        "label": "Banco Inter",
        "description": "Configuração para recebimento PIX via API do Banco Inter.",
        "fields": [
            {"key": "client_id", "label": "Client ID", "secret": True},
            {"key": "client_secret", "label": "Client Secret", "secret": True},
            {"key": "pix_key", "label": "Chave PIX", "secret": True},
        ],
        "required": ["client_id", "client_secret"],
    },
}
MASTER_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()

# Social login (public IDs are safe to expose; secrets stay server-side).
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
FACEBOOK_APP_ID = os.getenv("FACEBOOK_APP_ID", "").strip()
FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "").strip()
FACEBOOK_GRAPH_VERSION = os.getenv("FACEBOOK_GRAPH_VERSION", "v26.0").strip() or "v26.0"
SOCIAL_REAUTH_MINUTES = int(os.getenv("SOCIAL_REAUTH_MINUTES", "15") or "15")

def payment_fernet():
    if not PAYMENT_CONFIG_SECRET:
        return None
    raw = hashlib.sha256(PAYMENT_CONFIG_SECRET.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_payment_credentials(data: dict) -> str:
    f = payment_fernet()
    if not f:
        raise HTTPException(500, "Configure PAYMENT_CONFIG_KEY no Render para proteger as credenciais de pagamento")
    payload = json.dumps(data or {}, ensure_ascii=False).encode("utf-8")
    return f.encrypt(payload).decode("utf-8")


def decrypt_payment_credentials(token: str | None) -> dict:
    if not token:
        return {}
    # Migration compatibility: V2.17.x could derive the encryption key from
    # Supabase/Admin secrets. V2.18 writes only with PAYMENT_CONFIG_KEY, but can
    # still read legacy ciphertext so an existing PagBank setup is not lost.
    candidates = []
    if PAYMENT_CONFIG_SECRET:
        candidates.append(PAYMENT_CONFIG_SECRET)
    if LEGACY_PAYMENT_CONFIG_SECRET and LEGACY_PAYMENT_CONFIG_SECRET not in candidates:
        candidates.append(LEGACY_PAYMENT_CONFIG_SECRET)
    for secret in candidates:
        raw = hashlib.sha256(secret.encode("utf-8")).digest()
        f = Fernet(base64.urlsafe_b64encode(raw))
        try:
            return json.loads(f.decrypt(token.encode("utf-8")).decode("utf-8"))
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
            continue
    return {}


try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_INTEGRITY = psycopg.IntegrityError
except Exception:  # Local SQLite can run even before psycopg is installed.
    psycopg = None
    dict_row = None
    class PSYCOPG_INTEGRITY(Exception):
        pass

DBIntegrityError = (sqlite3.IntegrityError, PSYCOPG_INTEGRITY)

app = FastAPI(title="ClassificaJá API", version="2.18.9")
_cors = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# Lightweight in-process abuse protection. It intentionally covers only expensive
# or security-sensitive endpoints, so normal catalog browsing remains unaffected.
_rate_buckets = defaultdict(deque)
_rate_lock = threading.Lock()
_RATE_RULES = [
    ("POST", "/api/auth/login", 10, 60),
    ("POST", "/api/auth/register", 5, 600),
    ("POST", "/api/auth/social", 15, 60),
    ("POST", "/api/auth/forgot-password", 5, 900),
    ("POST", "/api/auth/resend-verification", 5, 900),
    ("POST", "/api/payments", 10, 60),
    ("POST_PREFIX", "/api/products/", 80, 60),
    ("GET_PREFIX", "/api/products/", 180, 60),
    ("POST_PREFIX", "/api/conversations/", 60, 60),
]

def _request_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded[:80]
    return (request.client.host if request.client else "unknown")[:80]

def _rate_rule(method: str, path: str):
    for kind, target, limit, window in _RATE_RULES:
        if kind == method and path == target:
            return limit, window, target
        if kind == f"{method}_PREFIX" and path.startswith(target):
            return limit, window, target
    return None

@app.middleware("http")
async def security_rate_limit(request: Request, call_next):
    if RATE_LIMIT_ENABLED:
        rule = _rate_rule(request.method.upper(), request.url.path)
        if rule:
            limit, window, group = rule
            now = time.monotonic()
            key = (request.method.upper(), group, _request_ip(request))
            with _rate_lock:
                bucket = _rate_buckets[key]
                while bucket and bucket[0] <= now - window:
                    bucket.popleft()
                if len(bucket) >= limit:
                    retry = max(1, int(window - (now - bucket[0])))
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Muitas tentativas. Aguarde um pouco e tente novamente."},
                        headers={"Retry-After": str(retry)},
                    )
                bucket.append(now)
                # Prevent unbounded growth from one-off IP/path combinations.
                if len(_rate_buckets) > 10000:
                    stale = [k for k, v in list(_rate_buckets.items())[:2000] if not v or v[-1] <= now - 3600]
                    for k in stale:
                        _rate_buckets.pop(k, None)
    return await call_next(request)


def _pg_sql(sql: str):
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    if sql.lstrip().upper().startswith("INSERT OR IGNORE INTO"):
        sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO", 1).rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql.replace("?", "%s")


class Database:
    def __init__(self):
        self.last_rowcount = 0
        if USE_POSTGRES:
            if psycopg is None:
                raise RuntimeError("DATABASE_URL usa PostgreSQL, mas psycopg não está instalado")
            self.raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode=os.getenv("DB_SSLMODE", "require"))
        else:
            self.raw = sqlite3.connect(DB_PATH)
            self.raw.row_factory = sqlite3.Row
            self.raw.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql: str, params=()):
        cur = self.raw.execute(_pg_sql(sql) if USE_POSTGRES else sql, tuple(params))
        self.last_rowcount = cur.rowcount if getattr(cur, "rowcount", -1) is not None else 0
        return cur

    def executemany(self, sql: str, seq):
        # sqlite3.Connection exposes executemany(), but psycopg 3 performs it on a cursor.
        # Keep a single compatibility wrapper so the rest of the application can use
        # the same database API in local SQLite and production PostgreSQL/Supabase.
        if USE_POSTGRES:
            cur = self.raw.cursor()
            cur.executemany(_pg_sql(sql), [tuple(params) for params in seq])
        else:
            cur = self.raw.executemany(sql, seq)
        self.last_rowcount = cur.rowcount if getattr(cur, "rowcount", -1) is not None else 0
        return cur

    def executescript(self, script: str):
        if not USE_POSTGRES:
            return self.raw.executescript(script)
        # Schema statements in this project contain no semicolons inside strings.
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    @property
    def total_changes(self):
        return max(self.last_rowcount, 0)

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            try:
                self.rollback()
            except Exception:
                pass
        self.close()
        return False


def conn():
    return Database()


def now_dt():
    return datetime.now(timezone.utc)


def now_iso():
    return now_dt().isoformat()


def hash_password(password: str, salt: bytes | None = None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000)
    return base64.b64encode(salt).decode(), base64.b64encode(digest).decode()


def verify_password(password: str, salt_b64: str, digest_b64: str):
    if not password or not salt_b64 or not digest_b64:
        return False
    try:
        salt = base64.b64decode(salt_b64)
        _, candidate = hash_password(password, salt)
        return secrets.compare_digest(candidate, digest_b64)
    except Exception:
        return False


def session_token_key(token: str) -> str:
    """Store new session tokens only as SHA-256 digests; legacy plaintext tokens remain valid."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()

def _token_candidates(token: str):
    return (token, session_token_key(token))

def _account_token(user_id: str, purpose: str, version: str = "", minutes: int = 60) -> str:
    if not ACCOUNT_TOKEN_SECRET:
        raise HTTPException(503, "Configure ACCOUNT_TOKEN_SECRET para habilitar links de segurança por e-mail")
    payload = {
        "uid": user_id, "purpose": purpose, "version": version,
        "exp": int(time.time()) + max(5, minutes) * 60, "nonce": secrets.token_hex(8),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(ACCOUNT_TOKEN_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def _read_account_token(token: str, purpose: str) -> dict:
    try:
        body, signature = str(token or "").rsplit(".", 1)
        expected = hmac.new(ACCOUNT_TOKEN_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not ACCOUNT_TOKEN_SECRET or not secrets.compare_digest(signature, expected):
            raise ValueError
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("purpose") != purpose or int(payload.get("exp") or 0) < int(time.time()):
            raise ValueError
        return payload
    except Exception:
        raise HTTPException(400, "Link inválido ou expirado")

def _send_email(to_email: str, subject: str, text: str) -> bool:
    if not (SMTP_HOST and SMTP_FROM and to_email):
        return False
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            if SMTP_USE_TLS:
                smtp.starttls()
            if SMTP_USER:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as exc:
        print(f"[email] Falha no envio para {to_email}: {exc}")
        return False

def _send_verification_email(row) -> bool:
    version = hashlib.sha256((str(_row_value(row, "email", "")) + str(_row_value(row, "created_at", ""))).encode()).hexdigest()[:16]
    token = _account_token(row["id"], "verify-email", version, minutes=24 * 60)
    base = PUBLIC_BASE_URL or "http://localhost:8000"
    link = f"{base}/api/auth/verify-email?token={quote(token)}"
    return _send_email(
        row["email"],
        "Confirme seu e-mail no ClassificaJá",
        f"Olá, {_row_value(row, 'name', 'usuário')}!\n\nConfirme seu e-mail para liberar todos os recursos da sua conta:\n{link}\n\nO link expira em 24 horas.",
    )

def _send_password_reset_email(row) -> bool:
    version = hashlib.sha256(str(_row_value(row, "password_hash", "")).encode()).hexdigest()[:16]
    token = _account_token(row["id"], "reset-password", version, minutes=30)
    link = f"{FRONTEND_URL}/entrar?reset_token={quote(token)}"
    return _send_email(
        row["email"],
        "Redefinição de senha do ClassificaJá",
        f"Recebemos uma solicitação para redefinir sua senha.\n\nUse este link em até 30 minutos:\n{link}\n\nSe não foi você, ignore esta mensagem.",
    )

def table_columns(db, table: str):
    if USE_POSTGRES:
        rows = db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        ).fetchall()
        return {r["column_name"] for r in rows}
    return {r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(db, table: str, column: str, definition: str):
    if column not in table_columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_supabase_bucket():
    if not USE_SUPABASE_STORAGE:
        return
    try:
        import httpx
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        # Creating an existing bucket returns an error; either outcome is safe here.
        httpx.post(
            f"{SUPABASE_URL}/storage/v1/bucket",
            headers=headers,
            json={
                "id": SUPABASE_BUCKET,
                "name": SUPABASE_BUCKET,
                "public": True,
                "file_size_limit": 7340032,
                "allowed_mime_types": ["image/jpeg", "image/png", "image/webp"],
            },
            timeout=12,
        )
    except Exception as exc:
        print(f"[storage] Não foi possível validar/criar o bucket automaticamente: {exc}")


def _normalized_image(content: bytes, max_bytes: int) -> tuple[bytes, str, str]:
    if not content:
        raise HTTPException(400, "Imagem vazia")
    if len(content) > max_bytes:
        raise HTTPException(400, f"Imagem maior que {max_bytes // (1024 * 1024)} MB")
    try:
        Image.MAX_IMAGE_PIXELS = 40_000_000
        with Image.open(io.BytesIO(content)) as probe:
            fmt = (probe.format or "").upper()
            if fmt not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(400, "O arquivo enviado não é uma imagem JPG, PNG ou WEBP válida")
            probe.verify()
        with Image.open(io.BytesIO(content)) as original:
            width, height = original.size
            if width < 1 or height < 1 or width * height > 40_000_000:
                raise HTTPException(400, "Dimensões da imagem não suportadas")
            image = ImageOps.exif_transpose(original)
            fmt = (original.format or fmt).upper()
            output = io.BytesIO()
            if fmt == "JPEG":
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                image.save(output, "JPEG", quality=90, optimize=True)
                return output.getvalue(), ".jpg", "image/jpeg"
            if fmt == "PNG":
                if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
                    image = image.convert("RGBA")
                image.save(output, "PNG", optimize=True)
                return output.getvalue(), ".png", "image/png"
            if image.mode not in {"RGB", "RGBA", "L", "LA"}:
                image = image.convert("RGBA")
            image.save(output, "WEBP", quality=90, method=4)
            return output.getvalue(), ".webp", "image/webp"
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, "O arquivo enviado não é uma imagem válida")

async def _save_image(image: UploadFile, folder: str, local_prefix: str, max_mb: int):
    content = await image.read()
    safe_content, ext, mime = _normalized_image(content, max_mb * 1024 * 1024)
    filename = f"{folder}/{uuid.uuid4().hex}{ext}"
    if USE_SUPABASE_STORAGE:
        import httpx
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": mime,
            "x-upsert": "false",
        }
        url = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET)}/{quote(filename, safe='/')}"
        response = httpx.post(url, headers=headers, content=safe_content, timeout=30)
        if response.status_code >= 300:
            raise HTTPException(502, f"Falha ao enviar imagem ao Supabase Storage: {response.text[:180]}")
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
    local_name = f"{local_prefix}{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / local_name).write_bytes(safe_content)
    return f"/uploads/{local_name}"

async def save_product_image(image: UploadFile):
    return await _save_image(image, "products", "product_", 7)

async def save_partner_image(image: UploadFile):
    return await _save_image(image, "partners", "partner_", 7)

async def save_home_slide_image(image: UploadFile):
    return await _save_image(image, "home-slides", "home_slide_", 10)

async def save_profile_image(image: UploadFile):
    return await _save_image(image, "profiles", "profile_", 5)

def delete_product_image(image_url: str | None):
    if not image_url:
        return
    if USE_SUPABASE_STORAGE and image_url.startswith(SUPABASE_URL):
        marker = f"/storage/v1/object/public/{SUPABASE_BUCKET}/"
        if marker in image_url:
            object_path = unquote(image_url.split(marker, 1)[1])
            try:
                import httpx
                headers = {"apikey": SUPABASE_SECRET_KEY, "Authorization": f"Bearer {SUPABASE_SECRET_KEY}"}
                httpx.delete(
                    f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET)}/{quote(object_path, safe='/')}",
                    headers=headers,
                    timeout=12,
                )
            except Exception:
                pass
        return
    if image_url.startswith("/uploads/"):
        local_path = UPLOAD_DIR / Path(image_url).name
        if local_path.exists():
            local_path.unlink()


def delete_product_images(image_urls):
    seen = set()
    for url in image_urls or []:
        if url and url not in seen:
            seen.add(url)
            delete_product_image(url)


def init_db():
    with conn() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              email TEXT UNIQUE NOT NULL,
              phone TEXT,
              password_salt TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS categories (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT UNIQUE NOT NULL,
              slug TEXT UNIQUE NOT NULL,
              icon TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
              id TEXT PRIMARY KEY,
              seller_id TEXT NOT NULL,
              title TEXT NOT NULL,
              description TEXT NOT NULL,
              price REAL NOT NULL,
              category_slug TEXT NOT NULL,
              city TEXT NOT NULL,
              state TEXT NOT NULL,
              condition TEXT NOT NULL,
              image_url TEXT,
              featured INTEGER NOT NULL DEFAULT 0,
              views INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              FOREIGN KEY(seller_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS favorites (
              user_id TEXT NOT NULL,
              product_id TEXT NOT NULL,
              PRIMARY KEY(user_id, product_id),
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS conversations (
              id TEXT PRIMARY KEY,
              product_id TEXT NOT NULL,
              buyer_id TEXT NOT NULL,
              seller_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(product_id,buyer_id,seller_id),
              FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
              FOREIGN KEY(buyer_id) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(seller_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              conversation_id TEXT NOT NULL,
              sender_id TEXT NOT NULL,
              body TEXT NOT NULL,
              read_at TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
              FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hidden_conversations (
              user_id TEXT NOT NULL,
              conversation_id TEXT NOT NULL,
              hidden_at TEXT NOT NULL,
              PRIMARY KEY(user_id, conversation_id),
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reports (
              id TEXT PRIMARY KEY,
              reporter_id TEXT NOT NULL,
              product_id TEXT NOT NULL,
              reason TEXT NOT NULL,
              details TEXT,
              status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT NOT NULL,
              resolved_at TEXT,
              FOREIGN KEY(reporter_id) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS payment_orders (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              product_id TEXT,
              plan_code TEXT NOT NULL,
              amount REAL NOT NULL,
              method TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              external_id TEXT,
              created_at TEXT NOT NULL,
              paid_at TEXT,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
              id TEXT PRIMARY KEY,
              type TEXT NOT NULL,
              product_id TEXT,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS notification_reads (
              notification_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              read_at TEXT NOT NULL,
              PRIMARY KEY(notification_id,user_id),
              FOREIGN KEY(notification_id) REFERENCES notifications(id) ON DELETE CASCADE,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS plan_settings (
              code TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              amount REAL NOT NULL DEFAULT 0,
              days INTEGER NOT NULL DEFAULT 0,
              ad_limit INTEGER NOT NULL DEFAULT 1,
              boost INTEGER NOT NULL DEFAULT 0,
              free INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1,
              badge TEXT,
              tagline TEXT,
              features_json TEXT,
              limitations_json TEXT,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS publish_plan_access (
              user_id TEXT PRIMARY KEY,
              plan_code TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'ready',
              payment_order_id TEXT,
              product_id TEXT,
              selected_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(payment_order_id) REFERENCES payment_orders(id) ON DELETE SET NULL,
              FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
            );
            """
        )
        # Migrations for V1 installations.
        ensure_column(db, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
        ensure_column(db, "users", "verified", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "users", "status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(db, "users", "avatar_url", "TEXT")
        ensure_column(db, "users", "address_line", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "users", "neighborhood", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "users", "city", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "users", "state", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "users", "postal_code", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "users", "profile_review_status", "TEXT NOT NULL DEFAULT 'unverified'")
        ensure_column(db, "users", "profile_updated_at", "TEXT")
        ensure_column(db, "users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "users", "email_verification_source", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "users", "name_verification_status", "TEXT NOT NULL DEFAULT 'unverified'")
        ensure_column(db, "users", "phone_verification_status", "TEXT NOT NULL DEFAULT 'unverified'")
        ensure_column(db, "users", "address_verification_status", "TEXT NOT NULL DEFAULT 'unverified'")
        ensure_column(db, "users", "avatar_verification_status", "TEXT NOT NULL DEFAULT 'unverified'")
        ensure_column(db, "users", "auth_provider", "TEXT NOT NULL DEFAULT 'local'")
        ensure_column(db, "sessions", "auth_provider", "TEXT NOT NULL DEFAULT 'local'")
        ensure_column(db, "sessions", "authenticated_at", "TEXT")
        # V2.18 migrates legacy plaintext bearer tokens in-place to SHA-256.
        # Clients keep the original bearer token; authentication hashes it before lookup.
        legacy_sessions = db.execute("SELECT token FROM sessions").fetchall()
        for session_row in legacy_sessions:
            stored = str(session_row["token"] or "")
            is_sha256 = len(stored) == 64 and all(ch in "0123456789abcdef" for ch in stored.lower())
            if stored and not is_sha256:
                db.execute("UPDATE sessions SET token=? WHERE token=?", (session_token_key(stored), stored))
        db.execute("DELETE FROM sessions WHERE expires_at<=?", (now_iso(),))
        db.execute("UPDATE users SET profile_review_status='verified' WHERE verified=1 AND profile_review_status='unverified'")
        db.execute("UPDATE users SET email_verified=1 WHERE LOWER(email)=?", (MASTER_EMAIL,)) if MASTER_EMAIL else None
        db.execute("UPDATE sessions SET authenticated_at=? WHERE authenticated_at IS NULL OR authenticated_at=''", (now_iso(),))
        db.execute("""CREATE TABLE IF NOT EXISTS user_identities (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            provider_email TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(provider, provider_user_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")
        # V2.16.7 — verificação independente por dado.
        # Preserva aprovações antigas apenas quando o respectivo dado realmente existe.
        db.execute("UPDATE users SET email_verification_source='master' WHERE email_verified=1 AND (email_verification_source IS NULL OR email_verification_source='')")
        db.execute("UPDATE users SET email_verification_source='facebook' WHERE email_verified=1 AND id IN (SELECT user_id FROM user_identities WHERE provider='facebook')")
        db.execute("UPDATE users SET email_verification_source='google' WHERE email_verified=1 AND id IN (SELECT user_id FROM user_identities WHERE provider='google')")
        db.execute("""UPDATE users SET name_verification_status=
            CASE WHEN verified=1 AND TRIM(COALESCE(name,''))<>'' THEN 'verified'
                 WHEN profile_review_status='pending' AND TRIM(COALESCE(name,''))<>'' THEN 'pending'
                 ELSE name_verification_status END
            WHERE name_verification_status='unverified'""")
        db.execute("""UPDATE users SET phone_verification_status=
            CASE WHEN verified=1 AND TRIM(COALESCE(phone,''))<>'' THEN 'verified'
                 WHEN profile_review_status='pending' AND TRIM(COALESCE(phone,''))<>'' THEN 'pending'
                 ELSE phone_verification_status END
            WHERE phone_verification_status='unverified'""")
        db.execute("""UPDATE users SET address_verification_status=
            CASE WHEN verified=1 AND TRIM(COALESCE(address_line,''))<>'' AND TRIM(COALESCE(city,''))<>'' AND TRIM(COALESCE(state,''))<>'' AND TRIM(COALESCE(postal_code,''))<>'' THEN 'verified'
                 WHEN profile_review_status='pending' AND TRIM(COALESCE(address_line,''))<>'' THEN 'pending'
                 ELSE address_verification_status END
            WHERE address_verification_status='unverified'""")
        db.execute("""UPDATE users SET avatar_verification_status=
            CASE WHEN verified=1 AND TRIM(COALESCE(avatar_url,''))<>'' THEN 'verified'
                 WHEN profile_review_status='pending' AND TRIM(COALESCE(avatar_url,''))<>'' THEN 'pending'
                 ELSE avatar_verification_status END
            WHERE avatar_verification_status='unverified'""")
        # O selo geral só existe quando TODOS os dados obrigatórios estão verificados.
        db.execute("""UPDATE users SET verified=CASE WHEN
            email_verified=1 AND name_verification_status='verified' AND phone_verification_status='verified'
            AND address_verification_status='verified' AND avatar_verification_status='verified'
            THEN 1 ELSE 0 END""")
        db.execute("""UPDATE users SET profile_review_status=CASE
            WHEN verified=1 THEN 'verified'
            WHEN name_verification_status='pending' OR phone_verification_status='pending' OR address_verification_status='pending' OR avatar_verification_status='pending' THEN 'pending'
            ELSE 'unverified' END""")
        # V2.17.3 — a conta proprietária (ADMIN_EMAIL) é verificada automaticamente.
        # Ela não entra no fluxo de moderação que o próprio Master administra.
        if MASTER_EMAIL:
            db.execute("""UPDATE users SET verified=1,profile_review_status='verified',email_verified=1,email_verification_source='master',
                name_verification_status='verified',phone_verification_status='verified',address_verification_status='verified',avatar_verification_status='verified'
                WHERE LOWER(email)=? AND role='admin'""", (MASTER_EMAIL,))
        ensure_column(db, "products", "neighborhood", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "products", "status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(db, "products", "featured_until", "TEXT")
        ensure_column(db, "products", "boost_level", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "products", "updated_at", "TEXT")
        plan_limit_column_missing = "ad_limit" not in table_columns(db, "plan_settings")
        ensure_column(db, "plan_settings", "ad_limit", "INTEGER NOT NULL DEFAULT 1")
        db.execute("""CREATE TABLE IF NOT EXISTS payment_integrations (
            provider TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            mode TEXT NOT NULL DEFAULT 'sandbox',
            credentials_enc TEXT,
            updated_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS partner_ads (
            id TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            title TEXT NOT NULL,
            subtitle TEXT,
            image_url TEXT,
            target_url TEXT,
            placement TEXT NOT NULL DEFAULT 'both',
            plan_tier TEXT NOT NULL DEFAULT 'free',
            active INTEGER NOT NULL DEFAULT 1,
            owner_user_id TEXT,
            source TEXT NOT NULL DEFAULT 'admin',
            expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        ensure_column(db, "partner_ads", "plan_tier", "TEXT NOT NULL DEFAULT 'free'")
        ensure_column(db, "partner_ads", "owner_user_id", "TEXT")
        ensure_column(db, "partner_ads", "source", "TEXT NOT NULL DEFAULT 'admin'")
        ensure_column(db, "partner_ads", "expires_at", "TEXT")
        db.execute("""CREATE TABLE IF NOT EXISTS home_slides (
            id TEXT PRIMARY KEY,
            title TEXT,
            subtitle TEXT,
            image_url TEXT NOT NULL,
            target_url TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        # Migração dos anúncios de parceria antigos: quem já estava no topo mantém nível Premium.
        db.execute("UPDATE partner_ads SET plan_tier='premium' WHERE placement IN ('home_top','both') AND plan_tier='free'")
        db.execute("UPDATE partner_ads SET placement='auto' WHERE placement IN ('home_top','feed_end','both')")
        db.execute("""CREATE TABLE IF NOT EXISTS publish_plan_access (
            user_id TEXT PRIMARY KEY,
            plan_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready',
            payment_order_id TEXT,
            product_id TEXT,
            selected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS free_plan_usage (
            user_id TEXT PRIMARY KEY,
            product_id TEXT,
            used_at TEXT NOT NULL
        )""")
        # V2.18 — independent publishing entitlements prevent a second paid plan
        # from overwriting a plan that the customer already purchased.
        db.execute("""CREATE TABLE IF NOT EXISTS publish_entitlements (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plan_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready',
            payment_order_id TEXT,
            product_id TEXT,
            source_key TEXT UNIQUE,
            expires_at TEXT,
            selected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        ensure_column(db, "publish_entitlements", "expires_at", "TEXT")
        legacy_access_rows = db.execute("SELECT * FROM publish_plan_access").fetchall()
        for legacy_access in legacy_access_rows:
            legacy_data = dict(legacy_access)
            source_key = f"legacy:{legacy_data['user_id']}"
            db.execute(
                """INSERT INTO publish_entitlements(id,user_id,plan_code,status,payment_order_id,product_id,source_key,expires_at,selected_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_key) DO NOTHING""",
                (str(uuid.uuid4()), legacy_data["user_id"], legacy_data["plan_code"], legacy_data.get("status") or "ready",
                 legacy_data.get("payment_order_id"), legacy_data.get("product_id"), source_key, None,
                 legacy_data.get("selected_at") or now_iso(), legacy_data.get("updated_at") or now_iso()),
            )
        db.execute("""CREATE TABLE IF NOT EXISTS product_view_events (
            product_id TEXT NOT NULL,
            viewer_key TEXT NOT NULL,
            view_bucket TEXT NOT NULL,
            viewed_at TEXT NOT NULL,
            PRIMARY KEY(product_id, viewer_key, view_bucket),
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        )""")
        for provider in PAYMENT_PROVIDER_DEFS:
            db.execute(
                "INSERT OR IGNORE INTO payment_integrations(provider,enabled,is_default,mode,credentials_enc,updated_at) VALUES (?,?,?,?,?,?)",
                (provider, 0, 0, "sandbox", None, now_iso()),
            )
        ensure_column(db, "products", "image_urls", "TEXT")
        ensure_column(db, "products", "original_price", "REAL")
        ensure_column(db, "products", "payment_mode", "TEXT NOT NULL DEFAULT 'cash'")
        ensure_column(db, "products", "plan_code", "TEXT")
        ensure_column(db, "products", "plan_expires_at", "TEXT")
        ensure_column(db, "payment_orders", "provider", "TEXT")
        ensure_column(db, "payment_orders", "provider_payment_id", "TEXT")
        ensure_column(db, "payment_orders", "installments", "INTEGER")
        ensure_column(db, "payment_orders", "installment_source", "TEXT")
        ensure_column(db, "payment_orders", "provider_payload", "TEXT")
        ensure_column(db, "notifications", "target_user_id", "TEXT")
        ensure_column(db, "notifications", "conversation_id", "TEXT")

        # V2.18 — indexes for the catalog, chat, moderation and payments.
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_products_status_created ON products(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_products_category_status ON products(category_slug, status)",
            "CREATE INDEX IF NOT EXISTS idx_products_city_status ON products(city, status)",
            "CREATE INDEX IF NOT EXISTS idx_products_seller ON products(seller_id)",
            "CREATE INDEX IF NOT EXISTS idx_products_boost_created ON products(boost_level, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_conversations_buyer_updated ON conversations(buyer_id, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_conversations_seller_updated ON conversations(seller_id, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_target_created ON notifications(target_user_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_reports_status_created ON reports(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_payment_orders_user_status ON payment_orders(user_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_payment_orders_external ON payment_orders(external_id)",
            "CREATE INDEX IF NOT EXISTS idx_entitlements_user_status ON publish_entitlements(user_id, status, selected_at)",
            "CREATE INDEX IF NOT EXISTS idx_product_view_events_time ON product_view_events(product_id, viewed_at)",
        ]:
            db.execute(idx_sql)

        categories = [
            ("Veículos", "veiculos", "🚗"),
            ("Autopeças", "autopecas", "🔧"),
            ("Celulares", "celulares", "📱"),
            ("Eletrônicos", "eletronicos", "💻"),
            ("Casa e Móveis", "casa-moveis", "🛋️"),
            ("Moda", "moda", "👕"),
            ("Imóveis", "imoveis", "🏠"),
            ("Serviços", "servicos", "🧑‍🔧"),
            ("Ferramentas", "ferramentas", "🧰"),
            ("Outros", "outros", "📦"),
        ]
        db.executemany("INSERT OR IGNORE INTO categories(name,slug,icon) VALUES (?,?,?)", categories)

        for code, plan in PLANS.items():
            db.execute(
                """INSERT OR IGNORE INTO plan_settings(code,name,amount,days,ad_limit,boost,free,active,badge,tagline,features_json,limitations_json,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    code, plan.get("name", code), float(plan.get("amount") or 0), int(plan.get("days") or 0),
                    int(plan.get("ad_limit") or 1), int(plan.get("boost") or 0), 1 if plan.get("free") else 0, 1, plan.get("badge", ""),
                    plan.get("tagline", ""), json.dumps(plan.get("features", []), ensure_ascii=False),
                    json.dumps(plan.get("limitations", []), ensure_ascii=False), now_iso(),
                ),
            )
        # V2.18.1 — migração única dos limites por plano. Depois da primeira
        # execução os valores ficam editáveis pelo Painel Master e não são
        # sobrescritos novamente em cada inicialização.
        if plan_limit_column_missing:
            for code, plan in PLANS.items():
                db.execute(
                    "UPDATE plan_settings SET ad_limit=?,updated_at=? WHERE code=?",
                    (max(1, int(plan.get("ad_limit") or 1)), now_iso(), code),
                )
        # V2.18.2 — Premium passa de 15 para 10 anúncios. Ajustamos apenas
        # instalações que ainda estejam exatamente no padrão anterior (15),
        # preservando eventuais limites personalizados pelo administrador.
        db.execute(
            "UPDATE plan_settings SET ad_limit=10,updated_at=? WHERE code='boost_30' AND ad_limit=15",
            (now_iso(),),
        )
        # Regra comercial atual do Grátis: 1 anúncio por conta e 7 dias.
        # Atualiza instalações antigas que ainda tinham duração 0.
        db.execute(
            """UPDATE plan_settings
               SET days=7, amount=0, free=1, name=?, badge=?, tagline=?, features_json=?, limitations_json=?, updated_at=?
               WHERE code='boost_7'""",
            (
                PLANS["boost_7"]["name"], PLANS["boost_7"]["badge"], PLANS["boost_7"]["tagline"],
                json.dumps(PLANS["boost_7"]["features"], ensure_ascii=False),
                json.dumps(PLANS["boost_7"]["limitations"], ensure_ascii=False), now_iso(),
            ),
        )

        # Identifica anúncios antigos sem plano como anúncios gratuitos e aplica validade de 7 dias.
        legacy_free_rows = db.execute(
            """SELECT id,seller_id,created_at FROM products
               WHERE (plan_code IS NULL OR plan_code='') AND COALESCE(boost_level,0)=0 AND featured_until IS NULL"""
        ).fetchall()
        for legacy in legacy_free_rows:
            data = dict(legacy)
            try:
                created_dt = datetime.fromisoformat(data.get("created_at") or now_iso())
            except Exception:
                created_dt = now_dt()
            expires_at = (created_dt + timedelta(days=7)).isoformat()
            db.execute(
                "UPDATE products SET plan_code='boost_7',plan_expires_at=? WHERE id=?",
                (expires_at, data["id"]),
            )
            db.execute(
                """INSERT INTO free_plan_usage(user_id,product_id,used_at) VALUES (?,?,?)
                   ON CONFLICT(user_id) DO NOTHING""",
                (data["seller_id"], data["id"], data.get("created_at") or now_iso()),
            )

        # V2.18.1 — converte planos pagos ainda vigentes de versões anteriores
        # em acesso persistente da conta. Assim o cliente não perde o plano ao
        # excluir o anúncio que originalmente recebeu o destaque.
        paid_active_rows = db.execute(
            """SELECT id,seller_id,plan_code,boost_level,plan_expires_at,featured_until
               FROM products
               WHERE COALESCE(boost_level,0)>=2
                 AND ((plan_expires_at IS NOT NULL AND plan_expires_at>?)
                   OR (featured_until IS NOT NULL AND featured_until>?))""",
            (now_iso(), now_iso()),
        ).fetchall()
        for paid_row in paid_active_rows:
            data = dict(paid_row)
            plan_code = data.get("plan_code")
            if plan_code not in {"boost_15", "boost_30"}:
                plan_code = "boost_30" if int(data.get("boost_level") or 0) >= 3 else "boost_15"
            expiry_values = [x for x in (data.get("plan_expires_at"), data.get("featured_until")) if _parse_iso_dt(x)]
            expires_at = max(expiry_values, key=lambda x: _parse_iso_dt(x)) if expiry_values else None
            if expires_at:
                activate_account_plan_entitlement(db, data["seller_id"], plan_code, expires_at, None, data["id"])

        # Production admin comes from environment variables; demo data stays local-only by default.
        admin_email = MASTER_EMAIL
        admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        if admin_email:
            # Segurança de proprietário único: nenhuma outra conta pode manter role=admin.
            db.execute("UPDATE users SET role='user' WHERE LOWER(email)<>? AND role='admin'", (admin_email,))
            existing_admin = db.execute("SELECT * FROM users WHERE LOWER(email)=?", (admin_email,)).fetchone()
            if not existing_admin and admin_password:
                salt, pwhash = hash_password(admin_password)
                db.execute(
                    "INSERT INTO users(id,name,email,phone,password_salt,password_hash,created_at,role,verified,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), os.getenv("ADMIN_NAME", "Administrador"), admin_email, os.getenv("ADMIN_PHONE", ""), salt, pwhash, now_iso(), "admin", 1, "active"),
                )
            elif existing_admin:
                # Promove somente o e-mail proprietário e mantém a senha já cadastrada.
                db.execute(
                    "UPDATE users SET role='admin', verified=1, status='active' WHERE LOWER(email)=?",
                    (admin_email,),
                )
            # O proprietário não entra na própria fila de moderação.
            db.execute("""UPDATE users SET verified=1,status='active',profile_review_status='verified',
                email_verified=1,email_verification_source='master',
                name_verification_status='verified',phone_verification_status='verified',
                address_verification_status='verified',avatar_verification_status='verified'
                WHERE LOWER(email)=? AND role='admin'""", (admin_email,))

        if SEED_DEMO_DATA:
            admin_id = "demo-admin"
            if not db.execute("SELECT 1 FROM users WHERE id=?", (admin_id,)).fetchone():
                salt, pwhash = hash_password("Admin123!")
                db.execute(
                    "INSERT INTO users(id,name,email,phone,password_salt,password_hash,created_at,role,verified,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (admin_id, "Administrador", "admin@classificaja.com", "45999999999", salt, pwhash, now_iso(), "admin", 1, "active"),
                )
            demo_id = "demo-seller"
            if not db.execute("SELECT 1 FROM users WHERE id=?", (demo_id,)).fetchone():
                salt, pwhash = hash_password("123456")
                db.execute(
                    "INSERT INTO users(id,name,email,phone,password_salt,password_hash,created_at,role,verified,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (demo_id, "Loja Demonstração", "demo@classificaja.com", "45999999999", salt, pwhash, now_iso(), "user", 1, "active"),
                )
            if db.execute("SELECT COUNT(*) n FROM products").fetchone()["n"] == 0:
                demos = [
                    ("iPhone 15 128 GB seminovo", 3899.90, "celulares", "Cascavel", "PR", "Centro", "Seminovo", 1, 128),
                    ("Jogo de rodas aro 17", 1690.00, "autopecas", "Cascavel", "PR", "Neva", "Usado", 1, 74),
                    ("Notebook Ryzen 7 16 GB", 3290.00, "eletronicos", "Toledo", "PR", "Jardim Porto Alegre", "Seminovo", 0, 96),
                    ("Sofá retrátil 3 lugares", 1250.00, "casa-moveis", "Cascavel", "PR", "Coqueiral", "Usado", 0, 51),
                    ("Honda CG 160 2023", 16900.00, "veiculos", "Foz do Iguaçu", "PR", "Centro", "Usado", 1, 245),
                    ("Kit ferramentas profissional", 479.90, "ferramentas", "Cascavel", "PR", "Pacaembu", "Novo", 0, 38),
                ]
                for title, price, cat, city, state, neighborhood, condition, featured, views in demos:
                    db.execute(
                        """INSERT INTO products(id,seller_id,title,description,price,category_slug,city,state,neighborhood,condition,image_url,featured,views,status,created_at,updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (str(uuid.uuid4()), demo_id, title, "Produto demonstrativo do ClassificaJá. Entre em contato com o vendedor para combinar detalhes.", price, cat, city, state, neighborhood, condition, None, featured, views, "active", now_iso(), now_iso()),
                    )
        # Parcerias são benefício exclusivo dos planos Plus e Premium.
        legacy_partner_texts = {
            "Sem participação na vitrine de parceiros",
            "1 campanha de parceria por mês em posições Plus",
            "Até 2 campanhas de parceria por mês com prioridade Premium",
            "Parceria básica: exibição em áreas de menor destaque (fim do feed e rodapé de anúncios)",
            "Parceria Plus: presença no feed e em áreas intermediárias das páginas de anúncios",
            "Parceria Premium: prioridade máxima após categorias e nas áreas nobres das páginas de anúncios",
            "Exibição no slider principal da página inicial",
        }
        partner_benefits = {
            "boost_15": "Parceria Plus: 1 campanha por mês no feed e em áreas intermediárias das páginas de anúncios",
            "boost_30": "Parceria Premium: até 2 campanhas por mês com prioridade máxima após categorias e nas áreas nobres das páginas de anúncios",
        }
        for plan_code in ("boost_7", "boost_15", "boost_30"):
            row = db.execute("SELECT features_json,limitations_json FROM plan_settings WHERE code=?", (plan_code,)).fetchone()
            if not row:
                continue
            try:
                features = json.loads(row["features_json"] or "[]")
            except Exception:
                features = []
            try:
                limitations = json.loads(row["limitations_json"] or "[]")
            except Exception:
                limitations = []
            features = [x for x in features if x not in legacy_partner_texts and not str(x).startswith("Parceria ")]
            limitations = [x for x in limitations if x not in legacy_partner_texts and not str(x).startswith("Parceria ")]
            if plan_code == "boost_7":
                limitation = "Sem participação em espaços de parceria"
                if limitation not in limitations:
                    limitations.append(limitation)
            else:
                features.append(partner_benefits[plan_code])
            db.execute(
                "UPDATE plan_settings SET features_json=?,limitations_json=?,updated_at=? WHERE code=?",
                (json.dumps(features, ensure_ascii=False), json.dumps(limitations, ensure_ascii=False), now_iso(), plan_code),
            )

        # Regra comercial: anúncios de parceria antigos vinculados ao nível grátis/básico
        # deixam de ser exibidos. Permanecem salvos no Master apenas para revisão/migração.
        db.execute("UPDATE partner_ads SET active=0,updated_at=? WHERE plan_tier='free' AND active=1", (now_iso(),))
        db.commit()
        ensure_supabase_bucket()


@app.on_event("startup")
def startup():
    init_db()


class RegisterIn(BaseModel):
    name: str
    email: str
    phone: str = ""
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class SocialLoginIn(BaseModel):
    provider: str
    credential: str


class MessageIn(BaseModel):
    body: str


class ReportIn(BaseModel):
    reason: str
    details: str = ""


class PaymentIn(BaseModel):
    product_id: Optional[str] = None
    plan_code: str
    method: str = "pix"
    tax_id: Optional[str] = None


class RenewPlanIn(BaseModel):
    method: str = "pix"
    tax_id: Optional[str] = None


class ModerationIn(BaseModel):
    status: str


class VerifyIn(BaseModel):
    verified: bool


class ProfileUpdateIn(BaseModel):
    current_password: str = ""
    name: str
    phone: str = ""
    address_line: str = ""
    neighborhood: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""


class PasswordChangeIn(BaseModel):
    current_password: str = ""
    new_password: str


class EmailOnlyIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


class AdminUserStatusIn(BaseModel):
    status: str


class AdminUserRoleIn(BaseModel):
    role: str


class AdminPlanIn(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    days: Optional[int] = None
    ad_limit: Optional[int] = None
    active: Optional[bool] = None
    badge: Optional[str] = None
    tagline: Optional[str] = None
    features: Optional[list[str]] = None
    limitations: Optional[list[str]] = None


class PartnerAdIn(BaseModel):
    company_name: str
    title: str
    subtitle: Optional[str] = ""
    image_url: Optional[str] = ""
    target_url: Optional[str] = ""
    placement: str = "auto"
    plan_tier: str = "plus"
    active: bool = True


class HomeSlideIn(BaseModel):
    title: Optional[str] = ""
    subtitle: Optional[str] = ""
    image_url: str
    target_url: Optional[str] = ""
    active: bool = True
    sort_order: int = 0


class MyPartnerAdIn(BaseModel):
    company_name: str
    title: str
    subtitle: Optional[str] = ""
    image_url: Optional[str] = ""
    target_url: Optional[str] = ""


PLANS = {
    "boost_7": {
        "name": "Plano Grátis",
        "amount": 0.0,
        "days": 7,
        "ad_limit": 1,
        "boost": 0,
        "free": True,
        "badge": "Grátis",
        "tagline": "1 anúncio gratuito por conta, disponível por 7 dias.",
        "features": [
            "1 anúncio gratuito por conta",
            "7 dias de publicação"
        ],
        "limitations": [
            "Uso gratuito disponível uma única vez por conta",
            "Após 7 dias o anúncio é pausado",
            "Sem selo de destaque",
            "Sem prioridade nas buscas",
            "Sem impulsionamento",
            "Sem posição privilegiada no catálogo",
            "Sem participação na vitrine de parceiros"
        ]
    },
    "boost_15": {
        "name": "Destaque Plus 15 dias",
        "amount": 34.90,
        "days": 15,
        "ad_limit": 5,
        "boost": 2,
        "free": False,
        "badge": "Mais vendido",
        "tagline": "Mais visibilidade e melhor posição para acelerar a venda.",
        "features": [
            "Selo de anúncio em destaque",
            "Prioridade maior nas buscas",
            "15 dias em evidência",
            "Melhor posição no catálogo",
            "1 campanha de parceria por mês em posições Plus"
        ],
        "limitations": []
    },
    "boost_30": {
        "name": "Destaque Premium 30 dias",
        "amount": 59.90,
        "days": 30,
        "ad_limit": 10,
        "boost": 3,
        "free": False,
        "badge": "Mais completo",
        "tagline": "O máximo de visibilidade para vender com mais velocidade.",
        "features": [
            "Tudo do plano Plus",
            "Prioridade máxima nas buscas",
            "30 dias de destaque premium",
            "Mais visualizações no catálogo",
            "Maior exposição entre os anúncios",
            "Até 2 campanhas de parceria por mês com prioridade Premium"
        ],
        "limitations": []
    },
}


PLAN_BY_BOOST = {
    1: {"code": "legacy_basic", "name": "Básico legado", "days": 7},
    2: {"code": "boost_15", "name": "Plus", "days": 15},
    3: {"code": "boost_30", "name": "Premium", "days": 30},
}


def plan_meta_from_boost(boost_level: int | None):
    try:
        boost = int(boost_level or 0)
    except Exception:
        boost = 0
    return PLAN_BY_BOOST.get(boost)


def plan_row_to_dict(row):
    data = dict(row)
    def _loads(value):
        if not value:
            return []
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return {
        "code": data["code"],
        "name": data["name"],
        "amount": float(data.get("amount") or 0),
        "days": int(data.get("days") or 0),
        "ad_limit": max(1, int(data.get("ad_limit") or 1)),
        "boost": int(data.get("boost") or 0),
        "free": bool(data.get("free")),
        "active": bool(data.get("active")),
        "badge": data.get("badge") or "",
        "tagline": data.get("tagline") or "",
        "features": _loads(data.get("features_json")),
        "limitations": _loads(data.get("limitations_json")),
        "updated_at": data.get("updated_at"),
    }


def get_plan_catalog(db=None, include_inactive=False):
    owns = db is None
    ctx = conn() if owns else None
    handle = ctx.__enter__() if owns else db
    try:
        where = "" if include_inactive else " WHERE active=1"
        rows = handle.execute(f"SELECT * FROM plan_settings{where} ORDER BY boost ASC, amount ASC").fetchall()
        if rows:
            return [plan_row_to_dict(r) for r in rows]
        return [{"code": code, "active": True, **plan} for code, plan in PLANS.items()]
    finally:
        if owns:
            ctx.__exit__(None, None, None)


def get_plan(code: str, db=None, include_inactive=False):
    plans = get_plan_catalog(db, include_inactive=include_inactive)
    return next((p for p in plans if p.get("code") == code), None)


def set_publish_plan_access(db, user_id: str, plan_code: str, status: str = "ready", payment_order_id: str | None = None, product_id: str | None = None, expires_at: str | None = None):
    """Create/update one entitlement without destroying other paid purchases."""
    now = now_iso()
    source_key = f"payment:{payment_order_id}" if payment_order_id else (f"free:{user_id}" if plan_code == "boost_7" else f"manual:{user_id}:{uuid.uuid4().hex}")
    existing = db.execute("SELECT id FROM publish_entitlements WHERE source_key=?", (source_key,)).fetchone()
    if existing:
        db.execute(
            "UPDATE publish_entitlements SET plan_code=?,status=?,product_id=?,expires_at=?,updated_at=? WHERE id=?",
            (plan_code, status, product_id, expires_at, now, existing["id"]),
        )
        entitlement_id = existing["id"]
    else:
        entitlement_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO publish_entitlements(id,user_id,plan_code,status,payment_order_id,product_id,source_key,expires_at,selected_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (entitlement_id, user_id, plan_code, status, payment_order_id, product_id, source_key, expires_at, now, now),
        )
    # Keep the legacy table synchronized for older deployments/frontends.
    db.execute(
        """INSERT INTO publish_plan_access(user_id,plan_code,status,payment_order_id,product_id,selected_at,updated_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET plan_code=excluded.plan_code,status=excluded.status,
             payment_order_id=excluded.payment_order_id,product_id=excluded.product_id,
             selected_at=excluded.selected_at,updated_at=excluded.updated_at""",
        (user_id, plan_code, status, payment_order_id, product_id, now, now),
    )
    return entitlement_id


def activate_account_plan_entitlement(db, user_id: str, plan_code: str, expires_at: str, payment_order_id: str | None = None, product_id: str | None = None):
    """Persist an account-level paid plan so deleting its first ad does not erase access."""
    if not expires_at:
        return None
    now = now_iso()
    source_key = f"account:{user_id}:{plan_code}"
    row = db.execute("SELECT * FROM publish_entitlements WHERE source_key=?", (source_key,)).fetchone()
    if row:
        data = dict(row)
        current_exp = _parse_iso_dt(data.get("expires_at"))
        incoming_exp = _parse_iso_dt(expires_at)
        best_exp = expires_at
        if current_exp and incoming_exp and current_exp > incoming_exp:
            best_exp = data.get("expires_at")
        db.execute(
            """UPDATE publish_entitlements
               SET status='active',expires_at=?,payment_order_id=COALESCE(?,payment_order_id),
                   product_id=COALESCE(?,product_id),updated_at=?
               WHERE id=?""",
            (best_exp, payment_order_id, product_id, now, data["id"]),
        )
        return data["id"]
    entitlement_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO publish_entitlements(id,user_id,plan_code,status,payment_order_id,product_id,source_key,expires_at,selected_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (entitlement_id, user_id, plan_code, "active", payment_order_id, product_id, source_key, expires_at, now, now),
    )
    return entitlement_id

def _parse_iso_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _stored_ads_count(db, user_id: str) -> int:
    """Count listings that still consume database/storage space.

    Deleted listings are physically removed and therefore free a slot. Paused,
    sold and expired listings still occupy storage and deliberately keep using a
    slot until the owner deletes them. This prevents users from bypassing the
    quota simply by pausing an ad.
    """
    row = db.execute("SELECT COUNT(*) n FROM products WHERE seller_id=?", (user_id,)).fetchone()
    return int(row["n"] or 0) if row else 0


def _active_product_plan(db, user_id: str):
    """Return the strongest still-valid account plan inferred from listings.

    V2.18 and older attached the paid plan to the first/individual listing. For
    V2.18.1 we treat a valid paid listing as proof that the account plan is
    active until its expiration. This migrates existing customers without
    asking them to pay again.
    """
    now = now_iso()
    rows = db.execute(
        """SELECT plan_code,plan_expires_at,featured_until,boost_level
           FROM products
           WHERE seller_id=?
             AND ((plan_expires_at IS NOT NULL AND plan_expires_at>?)
               OR (featured_until IS NOT NULL AND featured_until>?))
           ORDER BY boost_level DESC, COALESCE(plan_expires_at,featured_until) DESC""",
        (user_id, now, now),
    ).fetchall()
    best = None
    for row in rows:
        data = dict(row)
        plan_code = data.get("plan_code")
        if not plan_code:
            legacy_meta = plan_meta_from_boost(data.get("boost_level")) or {}
            plan_code = legacy_meta.get("code")
        plan = get_plan(plan_code, db, include_inactive=True)
        if not plan:
            continue
        expires_candidates = [
            x for x in (data.get("plan_expires_at"), data.get("featured_until")) if _parse_iso_dt(x)
        ]
        expires_at = max(expires_candidates, key=lambda x: _parse_iso_dt(x)) if expires_candidates else None
        expires_dt = _parse_iso_dt(expires_at)
        if not expires_dt or expires_dt <= now_dt():
            continue
        candidate = {
            "plan": plan,
            "expires_at": expires_at,
            "boost": int(plan.get("boost") or 0),
        }
        if not best:
            best = candidate
            continue
        if candidate["boost"] > best["boost"]:
            best = candidate
        elif candidate["boost"] == best["boost"] and expires_dt > (_parse_iso_dt(best.get("expires_at")) or now_dt()):
            best = candidate
    return best


def _ready_entitlement_plan(db, user_id: str):
    rows = db.execute(
        "SELECT * FROM publish_entitlements WHERE user_id=? AND status='ready' ORDER BY selected_at ASC",
        (user_id,),
    ).fetchall()
    best = None
    for row in rows:
        data = dict(row)
        plan = get_plan(data.get("plan_code"), db, include_inactive=True)
        if not plan:
            continue
        candidate = {"row": data, "plan": plan, "boost": int(plan.get("boost") or 0)}
        if not best or candidate["boost"] > best["boost"]:
            best = candidate
    return best, len(rows)


def _active_entitlement_plan(db, user_id: str):
    rows = db.execute(
        """SELECT * FROM publish_entitlements
           WHERE user_id=? AND status='active' AND expires_at IS NOT NULL AND expires_at>?
           ORDER BY expires_at DESC""",
        (user_id, now_iso()),
    ).fetchall()
    best = None
    for row in rows:
        data = dict(row)
        plan = get_plan(data.get("plan_code"), db, include_inactive=True)
        expires_dt = _parse_iso_dt(data.get("expires_at"))
        if not plan or not expires_dt or expires_dt <= now_dt():
            continue
        candidate = {
            "row": data,
            "plan": plan,
            "boost": int(plan.get("boost") or 0),
            "expires_at": data.get("expires_at"),
        }
        if not best:
            best = candidate
            continue
        if candidate["boost"] > best["boost"]:
            best = candidate
        elif candidate["boost"] == best["boost"] and expires_dt > (_parse_iso_dt(best.get("expires_at")) or now_dt()):
            best = candidate
    return best


def _last_paid_plan_state(db, user_id: str):
    """Return the most recent paid plan even when it has already expired.

    This is used to enforce renewal/upgrade rules: a former Premium customer
    cannot downgrade to Plus/Free, while a former Plus customer may renew Plus
    or upgrade to Premium.
    """
    row = db.execute(
        """SELECT plan_code,expires_at,updated_at,selected_at
           FROM publish_entitlements
           WHERE user_id=? AND plan_code IN ('boost_15','boost_30')
           ORDER BY COALESCE(expires_at,updated_at,selected_at) DESC
           LIMIT 1""",
        (user_id,),
    ).fetchone()
    if row:
        data = dict(row)
        plan = get_plan(data.get("plan_code"), db, include_inactive=True)
        if plan:
            return {"plan": plan, "expires_at": data.get("expires_at"), "source": "history_entitlement"}

    row = db.execute(
        """SELECT plan_code,paid_at,created_at
           FROM payment_orders
           WHERE user_id=? AND status='paid' AND plan_code IN ('boost_15','boost_30')
           ORDER BY COALESCE(paid_at,created_at) DESC
           LIMIT 1""",
        (user_id,),
    ).fetchone()
    if row:
        data = dict(row)
        plan = get_plan(data.get("plan_code"), db, include_inactive=True)
        if plan:
            return {"plan": plan, "expires_at": None, "source": "history_payment"}

    row = db.execute(
        """SELECT plan_code,plan_expires_at,featured_until,created_at
           FROM products
           WHERE seller_id=? AND plan_code IN ('boost_15','boost_30')
           ORDER BY COALESCE(plan_expires_at,featured_until,created_at) DESC
           LIMIT 1""",
        (user_id,),
    ).fetchone()
    if row:
        data = dict(row)
        plan = get_plan(data.get("plan_code"), db, include_inactive=True)
        if plan:
            return {
                "plan": plan,
                "expires_at": data.get("plan_expires_at") or data.get("featured_until"),
                "source": "history_product",
            }
    return None


def _allowed_paid_plan_codes(plan_code: str | None):
    if plan_code == "boost_30":
        return ["boost_30"]
    if plan_code == "boost_15":
        return ["boost_15", "boost_30"]
    return ["boost_15", "boost_30"]


def _plan_action_flags(plan_code: str | None):
    allowed = _allowed_paid_plan_codes(plan_code)
    return {
        "allowed_paid_plan_codes": allowed,
        "can_renew": plan_code in {"boost_15", "boost_30"},
        "can_upgrade": plan_code == "boost_15",
        "renew_plan_code": plan_code if plan_code in {"boost_15", "boost_30"} else None,
        "upgrade_plan_code": "boost_30" if plan_code == "boost_15" else None,
    }


def get_publish_plan_access(db, user_id: str):
    """Resolve the account publishing plan and its listing quota.

    Paid plans are account-level while valid. Existing V2.18 listings are used
    to infer the active plan, so customers who already show Plus/Premium in the
    dashboard can continue publishing without selecting/paying for the plan on
    every ad.
    """
    free_used = bool(db.execute("SELECT 1 FROM free_plan_usage WHERE user_id=?", (user_id,)).fetchone())
    ads_used = _stored_ads_count(db, user_id)
    active_product = _active_product_plan(db, user_id)
    active_entitlement = _active_entitlement_plan(db, user_id)
    entitlement, ready_count = _ready_entitlement_plan(db, user_id)

    chosen = None
    source = None
    entitlement_row = None
    expires_at = None

    active = None
    if active_product:
        active = {**active_product, "source": "active_plan"}
    if active_entitlement:
        if not active:
            active = {**active_entitlement, "source": "active_entitlement"}
        else:
            ent_boost = int(active_entitlement.get("boost") or 0)
            prod_boost = int(active.get("boost") or 0)
            ent_exp = _parse_iso_dt(active_entitlement.get("expires_at")) or now_dt()
            prod_exp = _parse_iso_dt(active.get("expires_at")) or now_dt()
            if ent_boost > prod_boost or (ent_boost == prod_boost and ent_exp > prod_exp):
                active = {**active_entitlement, "source": "active_entitlement"}

    if active:
        chosen = active["plan"]
        source = active.get("source") or "active_plan"
        expires_at = active.get("expires_at")

    if entitlement:
        ent_plan = entitlement["plan"]
        active_limit = max(1, int(chosen.get("ad_limit") or 1)) if chosen else 0
        active_remaining = max(0, active_limit - ads_used) if chosen else 0
        # A queued purchase activates when there is no active plan, when it is
        # an upgrade, or when the current plan has no remaining slots.
        if (
            not chosen
            or int(ent_plan.get("boost") or 0) > int(chosen.get("boost") or 0)
            or active_remaining <= 0
        ):
            chosen = ent_plan
            source = "entitlement"
            entitlement_row = entitlement["row"]
            expires_at = None  # starts when the first ad is published

    if not chosen:
        last_paid = _last_paid_plan_state(db, user_id)
        if last_paid:
            historical_plan = last_paid["plan"]
            historical_code = historical_plan.get("code")
            flags = _plan_action_flags(historical_code)
            return {
                "ready": False,
                "status": "expired",
                "plan": historical_plan,
                "ad_limit": max(1, int(historical_plan.get("ad_limit") or 1)),
                "ads_used": ads_used,
                "ads_remaining": 0,
                "expires_at": last_paid.get("expires_at"),
                "source": last_paid.get("source"),
                "free_used": free_used,
                "free_available": False,
                "ready_count": int(ready_count or 0),
                **flags,
            }
        return {
            "ready": False,
            "status": "none",
            "plan": None,
            "ad_limit": 0,
            "ads_used": ads_used,
            "ads_remaining": 0,
            "expires_at": None,
            "source": None,
            "free_used": free_used,
            "free_available": not free_used,
            "ready_count": int(ready_count or 0),
            **_plan_action_flags(None),
        }

    ad_limit = max(1, int(chosen.get("ad_limit") or 1))
    ads_remaining = max(0, ad_limit - ads_used)
    status = "ready" if source == "entitlement" else "active"
    if ads_remaining <= 0:
        status = "quota_full"

    return {
        "ready": ads_remaining > 0,
        "status": status,
        "entitlement_id": entitlement_row.get("id") if entitlement_row else None,
        "plan": chosen,
        "payment_order_id": entitlement_row.get("payment_order_id") if entitlement_row else None,
        "product_id": entitlement_row.get("product_id") if entitlement_row else None,
        "selected_at": entitlement_row.get("selected_at") if entitlement_row else None,
        "ad_limit": ad_limit,
        "ads_used": ads_used,
        "ads_remaining": ads_remaining,
        "expires_at": expires_at,
        "source": source,
        "free_used": free_used,
        "free_available": not free_used,
        "ready_count": int(ready_count or 0),
        **_plan_action_flags(chosen.get("code")),
    }

def create_session(db, user_id: str, provider: str = "local"):
    token = secrets.token_urlsafe(32)
    expires = (now_dt() + timedelta(days=30)).isoformat()
    authenticated_at = now_iso()
    db.execute(
        "INSERT INTO sessions(token,user_id,expires_at,auth_provider,authenticated_at) VALUES (?,?,?,?,?)",
        (session_token_key(token), user_id, expires, provider or "local", authenticated_at),
    )
    db.commit()
    return token


def user_public(row):
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    def value(key, default=""):
        return row[key] if key in keys and row[key] is not None else default
    return {
        "id": row["id"], "name": row["name"], "email": row["email"], "phone": value("phone"),
        "role": row["role"], "verified": bool(row["verified"]), "status": row["status"],
        "created_at": row["created_at"],
        "avatar_url": value("avatar_url"),
        "address_line": value("address_line"),
        "neighborhood": value("neighborhood"),
        "city": value("city"),
        "state": value("state"),
        "postal_code": value("postal_code"),
        "profile_review_status": value("profile_review_status", "verified" if bool(row["verified"]) else "unverified"),
        "profile_updated_at": value("profile_updated_at", None),
        "email_verified": bool(value("email_verified", 0)),
        "email_verification_source": value("email_verification_source", ""),
        "name_verification_status": value("name_verification_status", "unverified"),
        "phone_verification_status": value("phone_verification_status", "unverified"),
        "address_verification_status": value("address_verification_status", "unverified"),
        "avatar_verification_status": value("avatar_verification_status", "unverified"),
        "auth_provider": value("auth_provider", "local"),
        "has_password": bool(value("password_salt") and value("password_hash")),
        "is_master": bool(MASTER_EMAIL and str(row["email"]).strip().lower() == MASTER_EMAIL and str(row["role"]).lower() == "admin"),
    }


def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Faça login para continuar")
    token = authorization.split(" ", 1)[1]
    with conn() as db:
        raw_token, hashed_token = _token_candidates(token)
        row = db.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token IN (?,?) AND s.expires_at>?""",
            (raw_token, hashed_token, now_iso()),
        ).fetchone()
    if not row or row["status"] != "active":
        raise HTTPException(401, "Sessão inválida, expirada ou conta bloqueada")
    return dict(row)


def current_auth_context(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Faça login para continuar")
    token = authorization.split(" ", 1)[1]
    with conn() as db:
        raw_token, hashed_token = _token_candidates(token)
        row = db.execute(
            """SELECT u.*, s.auth_provider AS session_auth_provider, s.authenticated_at AS session_authenticated_at, s.token AS session_token
               FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token IN (?,?) AND s.expires_at>?""",
            (raw_token, hashed_token, now_iso()),
        ).fetchone()
    if not row or row["status"] != "active":
        raise HTTPException(401, "Sessão inválida ou expirada")
    return row


def _row_value(row, key, default=""):
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    return row[key] if key in keys and row[key] is not None else default


VERIFICATION_FIELDS = {
    "name": "name_verification_status",
    "phone": "phone_verification_status",
    "address": "address_verification_status",
    "avatar": "avatar_verification_status",
}


def _normalize_verification_status(value: str) -> str:
    return value if value in {"verified", "pending", "unverified"} else "unverified"


def _is_master_account(row) -> bool:
    if not row or not MASTER_EMAIL:
        return False
    return str(_row_value(row, "email", "")).strip().lower() == MASTER_EMAIL and str(_row_value(row, "role", "")).lower() == "admin"


def _recompute_user_verification(db, user_id: str):
    row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return None
    if _is_master_account(row):
        db.execute("""UPDATE users SET verified=1,profile_review_status='verified',email_verified=1,email_verification_source='master',
            name_verification_status='verified',phone_verification_status='verified',address_verification_status='verified',avatar_verification_status='verified'
            WHERE id=?""", (user_id,))
        return db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    complete = bool(_row_value(row, "email_verified", 0))
    complete = complete and all(
        _normalize_verification_status(str(_row_value(row, col, "unverified"))) == "verified"
        for col in VERIFICATION_FIELDS.values()
    )
    pending = any(
        _normalize_verification_status(str(_row_value(row, col, "unverified"))) == "pending"
        for col in VERIFICATION_FIELDS.values()
    )
    review_status = "verified" if complete else ("pending" if pending else "unverified")
    db.execute(
        "UPDATE users SET verified=?,profile_review_status=? WHERE id=?",
        (1 if complete else 0, review_status, user_id),
    )
    return db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def _address_is_complete(address_line: str, city: str, state: str, postal_code: str) -> bool:
    return bool(address_line.strip() and city.strip() and state.strip() and postal_code.strip())


def _has_password(row) -> bool:
    return bool(_row_value(row, "password_salt") and _row_value(row, "password_hash"))


def _social_session_is_recent(row) -> bool:
    provider = str(_row_value(row, "session_auth_provider", "local") or "local").lower()
    if provider not in {"google", "facebook"}:
        return False
    raw = _row_value(row, "session_authenticated_at", "")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return now_dt() - dt <= timedelta(minutes=max(1, SOCIAL_REAUTH_MINUTES))
    except Exception:
        return False


def _confirm_sensitive_action(row, current_password: str = ""):
    if _has_password(row):
        if not verify_password(current_password, _row_value(row, "password_salt"), _row_value(row, "password_hash")):
            raise HTTPException(401, "Senha atual incorreta")
        return
    if _social_session_is_recent(row):
        return
    provider = str(_row_value(row, "auth_provider", "social") or "social").title()
    raise HTTPException(401, f"Por segurança, entre novamente com {provider} para confirmar esta alteração")


def optional_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    with conn() as db:
        raw_token, hashed_token = _token_candidates(token)
        row = db.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token IN (?,?) AND s.expires_at>?",
            (raw_token, hashed_token, now_iso()),
        ).fetchone()
    return dict(row) if row and row["status"] == "active" else None


def admin_user(user=Depends(current_user)):
    if not MASTER_EMAIL:
        raise HTTPException(503, "Painel Master ainda não foi configurado no servidor")
    if str(user.get("email") or "").strip().lower() != MASTER_EMAIL or user.get("role") != "admin":
        raise HTTPException(403, "Acesso exclusivo do proprietário do ClassificaJá")
    return user


def cleanup_expired_features(db):
    db.execute("UPDATE products SET featured=0,boost_level=0 WHERE featured_until IS NOT NULL AND featured_until<=?", (now_iso(),))
    db.execute("UPDATE publish_entitlements SET status='used',updated_at=? WHERE status='active' AND expires_at IS NOT NULL AND expires_at<=?", (now_iso(), now_iso()))
    # Anúncios do plano gratuito ficam visíveis somente durante a validade do ciclo grátis.
    db.execute(
        """UPDATE products SET status='paused',updated_at=?
           WHERE status='active' AND plan_code='boost_7' AND plan_expires_at IS NOT NULL AND plan_expires_at<=?""",
        (now_iso(), now_iso()),
    )


def normalize_product_images(data):
    urls = []
    raw = data.get("image_urls")
    if raw:
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else list(raw)
            if isinstance(parsed, list):
                urls.extend([u for u in parsed if isinstance(u, str) and u.strip()])
        except Exception:
            pass
    primary = data.get("image_url")
    if primary and primary not in urls:
        urls.insert(0, primary)
    return urls[:8]


def product_dict(db, row, user_id: str | None = None):
    data = dict(row)
    seller = db.execute("SELECT id,name,phone,verified,created_at,avatar_url FROM users WHERE id=?", (data["seller_id"],)).fetchone()
    data["seller"] = dict(seller) if seller else None
    if data["seller"]:
        data["seller"]["verified"] = bool(data["seller"]["verified"])
    data["favorite"] = False
    if user_id:
        data["favorite"] = bool(db.execute("SELECT 1 FROM favorites WHERE user_id=? AND product_id=?", (user_id, data["id"])).fetchone())
    # Featured can be legacy flag or active paid period.
    paid_featured = False
    if data.get("featured_until"):
        try:
            paid_featured = datetime.fromisoformat(data["featured_until"]) > now_dt()
        except Exception:
            paid_featured = False
    data["featured_active"] = paid_featured if data.get("featured_until") else bool(data.get("featured"))
    data["images"] = normalize_product_images(data)
    if data["images"]:
        data["image_url"] = data["images"][0]
    try:
        original = float(data.get("original_price")) if data.get("original_price") is not None else None
    except Exception:
        original = None
    current = float(data.get("price") or 0)
    data["promo_active"] = bool(original and original > current)
    mode = str(data.get("payment_mode") or "cash").lower()
    if mode not in {"cash", "installments"}:
        mode = "cash"
    data["payment_mode"] = mode
    data["accepts_installments"] = mode == "installments"
    data["payment_mode_label"] = "Parcelamento disponível" if mode == "installments" else "À vista"
    data["free_plan"] = data.get("plan_code") == "boost_7"
    data["plan_expires_at"] = data.get("plan_expires_at")
    return data


def products_to_dicts(db, rows, user_id: str | None = None):
    """Serialize product lists with two bulk queries instead of an N+1 query per card."""
    rows = list(rows or [])
    if not rows:
        return []
    seller_ids = sorted({r["seller_id"] for r in rows if r["seller_id"]})
    sellers = {}
    if seller_ids:
        placeholders = ",".join("?" for _ in seller_ids)
        seller_rows = db.execute(
            f"SELECT id,name,verified,created_at,avatar_url FROM users WHERE id IN ({placeholders})",
            tuple(seller_ids),
        ).fetchall()
        sellers = {r["id"]: dict(r) for r in seller_rows}
        for seller in sellers.values():
            seller["verified"] = bool(seller.get("verified"))
    favorites = set()
    if user_id:
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" for _ in ids)
        fav_rows = db.execute(
            f"SELECT product_id FROM favorites WHERE user_id=? AND product_id IN ({placeholders})",
            (user_id, *ids),
        ).fetchall()
        favorites = {r["product_id"] for r in fav_rows}
    out = []
    for row in rows:
        data = dict(row)
        data["seller"] = sellers.get(data["seller_id"])
        data["favorite"] = data["id"] in favorites
        paid_featured = False
        if data.get("featured_until"):
            try:
                paid_featured = datetime.fromisoformat(data["featured_until"]) > now_dt()
            except Exception:
                pass
        data["featured_active"] = paid_featured if data.get("featured_until") else bool(data.get("featured"))
        data["images"] = normalize_product_images(data)
        if data["images"]:
            data["image_url"] = data["images"][0]
        try:
            original = float(data.get("original_price")) if data.get("original_price") is not None else None
        except Exception:
            original = None
        current = float(data.get("price") or 0)
        data["promo_active"] = bool(original and original > current)
        mode = str(data.get("payment_mode") or "cash").lower()
        if mode not in {"cash", "installments"}:
            mode = "cash"
        data["payment_mode"] = mode
        data["accepts_installments"] = mode == "installments"
        data["payment_mode_label"] = "Parcelamento disponível" if mode == "installments" else "À vista"
        data["free_plan"] = data.get("plan_code") == "boost_7"
        out.append(data)
    return out


@app.get("/api/health")
def health():
    return {"ok": True, "service": "ClassificaJá", "version": "2.18.9", "database": "postgresql" if USE_POSTGRES else "sqlite", "storage": "supabase" if USE_SUPABASE_STORAGE else "local"}


def _verify_google_credential(credential: str) -> dict:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Login com Google ainda não foi configurado")
    import httpx
    try:
        response = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
            timeout=15,
        )
    except httpx.RequestError:
        raise HTTPException(503, "Não foi possível validar o Google agora")
    if response.status_code != 200:
        raise HTTPException(401, "Credencial Google inválida ou expirada")
    data = response.json()
    if str(data.get("aud") or "") != GOOGLE_CLIENT_ID:
        raise HTTPException(401, "Credencial Google não pertence ao ClassificaJá")
    if str(data.get("iss") or "") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(401, "Emissor Google inválido")
    try:
        if int(data.get("exp") or 0) <= int(now_dt().timestamp()):
            raise HTTPException(401, "Credencial Google expirada")
    except (TypeError, ValueError):
        raise HTTPException(401, "Credencial Google inválida")
    email = str(data.get("email") or "").strip().lower()
    email_verified = str(data.get("email_verified") or "").lower() == "true"
    if not email or not email_verified:
        raise HTTPException(401, "O Google não confirmou um e-mail válido para esta conta")
    return {
        "provider": "google",
        "provider_user_id": str(data.get("sub") or ""),
        "email": email,
        "email_verified": True,
        "name": str(data.get("name") or email.split("@", 1)[0]).strip(),
        "avatar_url": str(data.get("picture") or "").strip(),
    }


def _verify_facebook_credential(credential: str) -> dict:
    if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET:
        raise HTTPException(503, "Login com Facebook ainda não foi configurado")
    import httpx
    app_token = f"{FACEBOOK_APP_ID}|{FACEBOOK_APP_SECRET}"
    base = f"https://graph.facebook.com/{FACEBOOK_GRAPH_VERSION}"
    try:
        debug = httpx.get(
            f"{base}/debug_token",
            params={"input_token": credential, "access_token": app_token},
            timeout=15,
        )
        debug.raise_for_status()
        info = (debug.json() or {}).get("data") or {}
        if not info.get("is_valid") or str(info.get("app_id") or "") != FACEBOOK_APP_ID:
            raise HTTPException(401, "Credencial Facebook inválida ou expirada")
        expires_at = int(info.get("expires_at") or 0)
        if expires_at and expires_at <= int(now_dt().timestamp()):
            raise HTTPException(401, "Credencial Facebook expirada")
        profile = httpx.get(
            f"{base}/me",
            params={"fields": "id,name,email,picture.type(large)", "access_token": credential},
            timeout=15,
        )
        profile.raise_for_status()
        data = profile.json() or {}
    except HTTPException:
        raise
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        raise HTTPException(503, "Não foi possível validar o Facebook agora")
    email = str(data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Sua conta do Facebook não forneceu um e-mail. Autorize o acesso ao e-mail para continuar")
    picture = (((data.get("picture") or {}).get("data") or {}).get("url") or "")
    return {
        "provider": "facebook",
        "provider_user_id": str(data.get("id") or ""),
        "email": email,
        # O token e o e-mail são obtidos diretamente da Graph API após validar o app/token.
        "email_verified": True,
        "name": str(data.get("name") or email.split("@", 1)[0]).strip(),
        "avatar_url": str(picture).strip(),
    }


def verify_social_credential(provider: str, credential: str) -> dict:
    provider = (provider or "").strip().lower()
    credential = (credential or "").strip()
    if not credential:
        raise HTTPException(400, "Credencial social ausente")
    if provider == "google":
        return _verify_google_credential(credential)
    if provider == "facebook":
        return _verify_facebook_credential(credential)
    raise HTTPException(400, "Provedor social não suportado")


@app.get("/api/auth/providers")
def auth_providers():
    return {
        "google": {"enabled": bool(GOOGLE_CLIENT_ID), "client_id": GOOGLE_CLIENT_ID if GOOGLE_CLIENT_ID else ""},
        "facebook": {
            "enabled": bool(FACEBOOK_APP_ID and FACEBOOK_APP_SECRET),
            "app_id": FACEBOOK_APP_ID if FACEBOOK_APP_ID else "",
            "graph_version": FACEBOOK_GRAPH_VERSION,
        },
    }


@app.post("/api/auth/social")
def social_login(payload: SocialLoginIn):
    identity = verify_social_credential(payload.provider, payload.credential)
    provider = identity["provider"]
    provider_user_id = identity["provider_user_id"]
    email = identity["email"]
    if not provider_user_id:
        raise HTTPException(401, "O provedor não retornou um identificador válido")
    new_user = False
    with conn() as db:
        linked = db.execute(
            """SELECT u.* FROM user_identities i JOIN users u ON u.id=i.user_id
               WHERE i.provider=? AND i.provider_user_id=?""",
            (provider, provider_user_id),
        ).fetchone()
        user = linked
        if not user:
            # O e-mail é a chave de reconciliação para evitar contas duplicadas.
            user = db.execute("SELECT * FROM users WHERE LOWER(email)=?", (email,)).fetchone()
            if user:
                db.execute(
                    "INSERT OR IGNORE INTO user_identities(id,user_id,provider,provider_user_id,provider_email,created_at) VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), user["id"], provider, provider_user_id, email, now_iso()),
                )
                updates = []
                params = []
                if identity.get("email_verified"):
                    updates.append("email_verified=1")
                    updates.append("email_verification_source=?")
                    params.append(provider)
                if identity.get("avatar_url") and not _row_value(user, "avatar_url", ""):
                    updates.append("avatar_url=?")
                    params.append(identity["avatar_url"] )
                if not _has_password(user):
                    updates.append("auth_provider=?")
                    params.append(provider)
                if updates:
                    params.append(user["id"] )
                    db.execute(f"UPDATE users SET {','.join(updates)} WHERE id=?", tuple(params))
                    user = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            else:
                new_user = True
                uid = str(uuid.uuid4())
                db.execute(
                    """INSERT INTO users(
                        id,name,email,phone,password_salt,password_hash,created_at,role,verified,status,
                        avatar_url,email_verified,email_verification_source,auth_provider,profile_review_status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        uid, identity.get("name") or email.split("@", 1)[0], email, "", "", "", now_iso(),
                        "user", 0, "active", identity.get("avatar_url") or None,
                        1 if identity.get("email_verified") else 0, provider if identity.get("email_verified") else "", provider, "unverified",
                    ),
                )
                db.execute(
                    "INSERT INTO user_identities(id,user_id,provider,provider_user_id,provider_email,created_at) VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), uid, provider, provider_user_id, email, now_iso()),
                )
                user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if user["status"] != "active":
            raise HTTPException(403, "Conta indisponível")
        token = create_session(db, user["id"], provider)
        user = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    return {"token": token, "user": user_public(user), "new_user": new_user, "provider": provider}


@app.post("/api/auth/register")
def register(payload: RegisterIn):
    if len(payload.password) < 8:
        raise HTTPException(400, "A senha precisa ter pelo menos 8 caracteres")
    name = payload.name.strip()
    email = payload.email.lower().strip()
    phone_digits = "".join(ch for ch in payload.phone if ch.isdigit())
    if len(name) < 2 or "@" not in email or email.startswith("@") or email.endswith("@"): 
        raise HTTPException(400, "Nome e e-mail válidos são obrigatórios")
    if phone_digits and len(phone_digits) not in {10, 11}:
        raise HTTPException(400, "Informe um WhatsApp brasileiro válido com DDD")
    uid = str(uuid.uuid4())
    salt, pwhash = hash_password(payload.password)
    try:
        with conn() as db:
            db.execute(
                """INSERT INTO users(id,name,email,phone,password_salt,password_hash,created_at,role,verified,status,email_verified,auth_provider)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, name, email, phone_digits, salt, pwhash, now_iso(), "user", 0, "active", 0, "local"),
            )
            token = create_session(db, uid, "local")
            row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    except DBIntegrityError:
        raise HTTPException(409, "Este e-mail já está cadastrado")
    email_sent = _send_verification_email(row) if ACCOUNT_TOKEN_SECRET else False
    return {"token": token, "user": user_public(row), "verification_email_sent": email_sent}


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1]
        raw_token, hashed_token = _token_candidates(raw)
        with conn() as db:
            db.execute("DELETE FROM sessions WHERE token IN (?,?)", (raw_token, hashed_token))
            db.commit()
    return {"ok": True}


@app.post("/api/auth/resend-verification")
def resend_verification(payload: EmailOnlyIn):
    email = payload.email.lower().strip()
    with conn() as db:
        row = db.execute("SELECT * FROM users WHERE LOWER(email)=?", (email,)).fetchone()
    sent = False
    if row and not bool(_row_value(row, "email_verified", 0)) and ACCOUNT_TOKEN_SECRET:
        sent = _send_verification_email(row)
    # Do not disclose whether an account exists.
    return {"ok": True, "message": "Se o e-mail estiver cadastrado e pendente, enviaremos um novo link.", "sent": sent if not USE_POSTGRES else None}


@app.get("/api/auth/verify-email")
def verify_email(token: str):
    payload = _read_account_token(token, "verify-email")
    with conn() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (payload["uid"],)).fetchone()
        if not row:
            raise HTTPException(400, "Conta não encontrada")
        expected_version = hashlib.sha256((str(_row_value(row, "email", "")) + str(_row_value(row, "created_at", ""))).encode()).hexdigest()[:16]
        if payload.get("version") != expected_version:
            raise HTTPException(400, "Link inválido")
        db.execute("UPDATE users SET email_verified=1,email_verification_source='email' WHERE id=?", (row["id"],))
        _recompute_user_verification(db, row["id"])
        db.commit()
    return RedirectResponse(f"{FRONTEND_URL}/entrar?verified=1", status_code=303)


@app.post("/api/auth/forgot-password")
def forgot_password(payload: EmailOnlyIn):
    email = payload.email.lower().strip()
    with conn() as db:
        row = db.execute("SELECT * FROM users WHERE LOWER(email)=?", (email,)).fetchone()
    if row and _has_password(row) and ACCOUNT_TOKEN_SECRET:
        _send_password_reset_email(row)
    return {"ok": True, "message": "Se existir uma conta com esse e-mail, você receberá as instruções de redefinição."}


@app.post("/api/auth/reset-password")
def reset_password(payload: ResetPasswordIn):
    if len(payload.new_password) < 8:
        raise HTTPException(400, "A nova senha precisa ter pelo menos 8 caracteres")
    token_data = _read_account_token(payload.token, "reset-password")
    with conn() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (token_data["uid"],)).fetchone()
        if not row:
            raise HTTPException(400, "Conta não encontrada")
        expected_version = hashlib.sha256(str(_row_value(row, "password_hash", "")).encode()).hexdigest()[:16]
        if token_data.get("version") != expected_version:
            raise HTTPException(400, "Este link já foi utilizado ou não é mais válido")
        salt, pwhash = hash_password(payload.new_password)
        db.execute("UPDATE users SET password_salt=?,password_hash=? WHERE id=?", (salt, pwhash, row["id"]))
        db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        db.commit()
    return {"ok": True, "message": "Senha redefinida. Faça login novamente."}


@app.post("/api/auth/login")
def login(payload: LoginIn):
    with conn() as db:
        user = db.execute("SELECT * FROM users WHERE LOWER(email)=?", (payload.email.lower().strip(),)).fetchone()
        if not user:
            raise HTTPException(401, "E-mail ou senha incorretos")
        if not _has_password(user):
            provider = str(_row_value(user, "auth_provider", "social") or "social").title()
            raise HTTPException(401, f"Esta conta usa login com {provider}. Entre pelo botão {provider} ou crie uma senha no seu painel")
        if not verify_password(payload.password, user["password_salt"], user["password_hash"]):
            raise HTTPException(401, "E-mail ou senha incorretos")
        if user["status"] != "active":
            raise HTTPException(403, "Conta indisponível")
        token = create_session(db, user["id"], "local")
    return {"token": token, "user": user_public(user)}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user_public(user)


@app.put("/api/me/profile")
def update_my_profile(payload: ProfileUpdateIn, user=Depends(current_auth_context)):
    _confirm_sensitive_action(user, payload.current_password)
    name = payload.name.strip()
    if len(name) < 2:
        raise HTTPException(400, "Informe um nome válido")
    phone_digits = "".join(ch for ch in payload.phone if ch.isdigit())
    if phone_digits and len(phone_digits) not in {10, 11}:
        raise HTTPException(400, "Informe um telefone brasileiro válido com DDD")
    postal_digits = "".join(ch for ch in payload.postal_code if ch.isdigit())
    if postal_digits and len(postal_digits) != 8:
        raise HTTPException(400, "Informe um CEP válido com 8 dígitos")
    state = payload.state.strip().upper()
    if state and len(state) != 2:
        raise HTTPException(400, "Use a sigla do estado com 2 letras")
    address_line = payload.address_line.strip()
    neighborhood = payload.neighborhood.strip()
    city = payload.city.strip()
    old_name = str(_row_value(user, "name", "") or "").strip()
    old_phone = "".join(ch for ch in str(_row_value(user, "phone", "") or "") if ch.isdigit())
    old_address = (
        str(_row_value(user, "address_line", "") or "").strip(),
        str(_row_value(user, "neighborhood", "") or "").strip(),
        str(_row_value(user, "city", "") or "").strip(),
        str(_row_value(user, "state", "") or "").strip().upper(),
        "".join(ch for ch in str(_row_value(user, "postal_code", "") or "") if ch.isdigit()),
    )
    new_address = (address_line, neighborhood, city, state, postal_digits)
    is_master = _is_master_account(user)
    name_status = "verified" if is_master else _normalize_verification_status(str(_row_value(user, "name_verification_status", "unverified")))
    phone_status = "verified" if is_master else _normalize_verification_status(str(_row_value(user, "phone_verification_status", "unverified")))
    address_status = "verified" if is_master else _normalize_verification_status(str(_row_value(user, "address_verification_status", "unverified")))
    changed = []
    if name != old_name:
        name_status = "verified" if is_master else "pending"
        changed.append("nome")
    if phone_digits != old_phone:
        phone_status = "verified" if is_master else ("pending" if phone_digits else "unverified")
        changed.append("telefone")
    if new_address != old_address:
        address_status = "verified" if is_master else ("pending" if _address_is_complete(address_line, city, state, postal_digits) else "unverified")
        changed.append("endereço")
    with conn() as db:
        db.execute(
            """UPDATE users SET name=?,phone=?,address_line=?,neighborhood=?,city=?,state=?,postal_code=?,
               name_verification_status=?,phone_verification_status=?,address_verification_status=?,profile_updated_at=? WHERE id=?""",
            (name, phone_digits, address_line, neighborhood, city, state, postal_digits,
             name_status, phone_status, address_status, now_iso(), user["id"]),
        )
        row = _recompute_user_verification(db, user["id"])
        db.commit()
    if is_master:
        message = "Dados da conta Master atualizados. A verificação é automática para o proprietário do site."
    else:
        message = "Nenhum dado verificado foi alterado." if not changed else "Somente os dados alterados foram enviados para verificação: " + ", ".join(changed) + "."
    return {"ok": True, "message": message, "user": user_public(row)}


@app.post("/api/me/avatar")
async def update_my_avatar(current_password: str = Form(""), image: UploadFile = File(...), user=Depends(current_auth_context)):
    _confirm_sensitive_action(user, current_password)
    new_url = await save_profile_image(image)
    old_url = _row_value(user, "avatar_url", "")
    is_master = _is_master_account(user)
    with conn() as db:
        db.execute(
            "UPDATE users SET avatar_url=?,avatar_verification_status=?,profile_updated_at=? WHERE id=?",
            (new_url, "verified" if is_master else "pending", now_iso(), user["id"]),
        )
        row = _recompute_user_verification(db, user["id"])
        db.commit()
    if old_url and old_url != new_url:
        delete_product_image(old_url)
    message = "Foto da conta Master atualizada com verificação automática." if is_master else "Foto atualizada. Somente a foto voltou para verificação do Master"
    return {"ok": True, "message": message, "user": user_public(row)}


@app.put("/api/me/password")
def update_my_password(payload: PasswordChangeIn, user=Depends(current_auth_context)):
    had_password = _has_password(user)
    if had_password:
        if not verify_password(payload.current_password, _row_value(user, "password_salt"), _row_value(user, "password_hash")):
            raise HTTPException(401, "Senha atual incorreta")
    elif not _social_session_is_recent(user):
        provider = str(_row_value(user, "auth_provider", "social") or "social").title()
        raise HTTPException(401, f"Entre novamente com {provider} antes de criar uma senha")
    if len(payload.new_password) < 8:
        raise HTTPException(400, "A nova senha precisa ter pelo menos 8 caracteres")
    if had_password and payload.current_password == payload.new_password:
        raise HTTPException(400, "A nova senha deve ser diferente da atual")
    salt, pwhash = hash_password(payload.new_password)
    with conn() as db:
        db.execute("UPDATE users SET password_salt=?,password_hash=? WHERE id=?", (salt, pwhash, user["id"]))
        current_session = _row_value(user, "session_token", "")
        if current_session:
            db.execute("DELETE FROM sessions WHERE user_id=? AND token<>?", (user["id"], current_session))
        else:
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        db.commit()
    return {"ok": True, "message": ("Senha alterada com sucesso. As outras sessões foram encerradas." if had_password else "Senha criada com sucesso. As outras sessões foram encerradas.")}


@app.get("/api/categories")
def categories():
    with conn() as db:
        rows = db.execute("SELECT * FROM categories ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/public/stats")
def public_stats():
    with conn() as db:
        products = db.execute("SELECT COUNT(*) n FROM products WHERE status='active'").fetchone()["n"]
        sellers = db.execute("SELECT COUNT(*) n FROM users WHERE status='active'").fetchone()["n"]
        cities = db.execute("SELECT COUNT(DISTINCT city) n FROM products WHERE status='active'").fetchone()["n"]
    return {"products": products, "sellers": sellers, "cities": cities}


PARTNER_SLOT_TIERS = {
    # Premium: todas as áreas, inclusive as posições mais nobres.
    "home_top": ("premium",),
    "product_top": ("premium",),
    # Plus também aparece em áreas intermediárias.
    "product_mid": ("premium", "plus"),
    # Final do feed e rodapé do anúncio: somente Plus e Premium.
    "feed_end": ("premium", "plus"),
    "product_end": ("premium", "plus"),
}


@app.get("/api/partner-ads")
def public_partner_ads(slot: str = "feed_end", placement: str = "", limit: int = 6):
    # placement é mantido como alias para versões antigas do frontend.
    slot = (slot or placement or "feed_end").strip().lower()
    if slot == "both":
        slot = "feed_end"
    tiers = PARTNER_SLOT_TIERS.get(slot)
    if not tiers:
        raise HTTPException(400, "Posição de parceria inválida")
    limit = max(1, min(int(limit or 6), 12))
    placeholders = ",".join("?" for _ in tiers)
    tier_order = "CASE plan_tier WHEN 'premium' THEN 3 WHEN 'plus' THEN 2 ELSE 1 END"
    with conn() as db:
        now = now_iso()
        rows = db.execute(
            f"""SELECT * FROM partner_ads
                WHERE active=1
                  AND plan_tier IN ({placeholders})
                  AND (expires_at IS NULL OR expires_at>?)
                  AND (source<>'user' OR EXISTS (
                    SELECT 1 FROM products p
                    WHERE p.seller_id=partner_ads.owner_user_id
                      AND p.featured=1 AND p.featured_until>?
                      AND p.boost_level >= CASE partner_ads.plan_tier WHEN 'premium' THEN 3 ELSE 2 END
                  ))
                ORDER BY {tier_order} DESC, RANDOM() LIMIT ?""",
            (*tiers, now, now, limit),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/home-slides")
def public_home_slides(limit: int = 8):
    limit = max(1, min(int(limit or 8), 12))
    with conn() as db:
        rows = db.execute(
            "SELECT * FROM home_slides WHERE active=1 ORDER BY sort_order ASC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/products")
def list_products(search: str = "", category: str = "", city: str = "", neighborhood: str = "", sort: str = "newest", limit: int = 50, offset: int = 0, user=Depends(optional_user)):
    where = ["status='active'"]
    args = []
    if search.strip():
        where.append("(LOWER(title) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?) OR LOWER(city) LIKE LOWER(?) OR LOWER(neighborhood) LIKE LOWER(?))")
        q = f"%{search.strip()}%"
        args += [q, q, q, q]
    if category.strip():
        where.append("category_slug=?")
        args.append(category.strip())
    if city.strip():
        where.append("LOWER(city) LIKE LOWER(?)")
        args.append(f"%{city.strip()}%")
    if neighborhood.strip():
        where.append("LOWER(neighborhood) LIKE LOWER(?)")
        args.append(f"%{neighborhood.strip()}%")
    order = {
        "newest": "boost_level DESC, created_at DESC",
        "price_low": "boost_level DESC, price ASC",
        "price_high": "boost_level DESC, price DESC",
        "popular": "boost_level DESC, views DESC",
    }.get(sort, "boost_level DESC, created_at DESC")
    with conn() as db:
        cleanup_expired_features(db)
        db.commit()
        safe_limit = max(1, min(int(limit or 50), 100))
        safe_offset = max(0, int(offset or 0))
        rows = db.execute(f"SELECT * FROM products WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ? OFFSET ?", (*args, safe_limit, safe_offset)).fetchall()
        return products_to_dicts(db, rows, user["id"] if user else None)


@app.get("/api/products/{product_id}")
def get_product(product_id: str, request: Request, user=Depends(optional_user)):
    with conn() as db:
        cleanup_expired_features(db)
        db.commit()
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row or (row["status"] != "active" and (not user or (row["seller_id"] != user["id"] and user["role"] != "admin"))):
            raise HTTPException(404, "Anúncio não encontrado")
        # Count at most one view per viewer/product/hour to reduce refresh/bot inflation.
        viewer_raw = f"user:{user['id']}" if user else f"ip:{_request_ip(request)}|ua:{request.headers.get('user-agent','')[:160]}"
        secret = (ACCOUNT_TOKEN_SECRET or "classificaja-view-v2.18").encode("utf-8")
        viewer_key = hmac.new(secret, viewer_raw.encode("utf-8"), hashlib.sha256).hexdigest()
        bucket = now_dt().strftime("%Y-%m-%dT%H")
        db.execute(
            "INSERT INTO product_view_events(product_id,viewer_key,view_bucket,viewed_at) VALUES (?,?,?,?) ON CONFLICT(product_id,viewer_key,view_bucket) DO NOTHING",
            (product_id, viewer_key, bucket, now_iso()),
        )
        if db.total_changes > 0:
            db.execute("UPDATE products SET views=views+1 WHERE id=?", (product_id,))
        db.commit()
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        return product_dict(db, row, user["id"] if user else None)


@app.get("/api/products/{product_id}/related")
def related_products(product_id: str, limit: int = 4, user=Depends(optional_user)):
    limit = max(1, min(int(limit or 4), 12))
    with conn() as db:
        cleanup_expired_features(db)
        db.commit()
        base = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not base:
            raise HTTPException(404, "Anúncio não encontrado")

        price = float(base["price"] or 0)
        low = max(0, price * 0.65)
        high = price * 1.35 if price > 0 else 999999999
        items = []
        seen = {product_id}

        def add_rows(rows):
            for row in rows:
                if row["id"] not in seen:
                    items.append(row)
                    seen.add(row["id"])
                    if len(items) >= limit:
                        return True
            return False

        # 1) Melhor correspondência: mesma categoria + preço semelhante,
        #    priorizando a mesma cidade.
        rows = db.execute(
            """SELECT * FROM products
               WHERE status='active' AND id<>? AND category_slug=? AND price BETWEEN ? AND ?
               ORDER BY CASE WHEN city=? THEN 0 ELSE 1 END,
                        ABS(price-?), boost_level DESC, created_at DESC
               LIMIT ?""",
            (product_id, base["category_slug"], low, high, base["city"], price, limit * 3),
        ).fetchall()
        if add_rows(rows):
            return products_to_dicts(db, items[:limit], user["id"] if user else None)

        # 2) Mesma categoria, mesmo que o preço seja diferente.
        rows = db.execute(
            """SELECT * FROM products
               WHERE status='active' AND id<>? AND category_slug=?
               ORDER BY CASE WHEN city=? THEN 0 ELSE 1 END,
                        ABS(price-?), boost_level DESC, created_at DESC
               LIMIT ?""",
            (product_id, base["category_slug"], base["city"], price, limit * 3),
        ).fetchall()
        if add_rows(rows):
            return products_to_dicts(db, items[:limit], user["id"] if user else None)

        # 3) Mesma cidade, qualquer categoria, priorizando preço próximo.
        rows = db.execute(
            """SELECT * FROM products
               WHERE status='active' AND id<>? AND city=?
               ORDER BY ABS(price-?), boost_level DESC, created_at DESC
               LIMIT ?""",
            (product_id, base["city"], price, limit * 3),
        ).fetchall()
        if add_rows(rows):
            return products_to_dicts(db, items[:limit], user["id"] if user else None)

        # 4) Último fallback: outros anúncios ativos do marketplace.
        rows = db.execute(
            """SELECT * FROM products
               WHERE status='active' AND id<>?
               ORDER BY ABS(price-?), boost_level DESC, views DESC, created_at DESC
               LIMIT ?""",
            (product_id, price, limit * 4),
        ).fetchall()
        add_rows(rows)

        return products_to_dicts(db, items[:limit], user["id"] if user else None)


@app.post("/api/products")
async def create_product(
    title: str = Form(...), description: str = Form(...), price: float = Form(...), category_slug: str = Form(...),
    city: str = Form(...), state: str = Form(...), neighborhood: str = Form(""), condition: str = Form("Usado"),
    original_price: float | None = Form(default=None), payment_mode: str = Form("cash"),
    images: list[UploadFile] = File(default=[]), image: UploadFile | None = File(default=None), user=Depends(current_user),
):
    title = title.strip()
    description = description.strip()
    city = city.strip()
    state = state.strip().upper()
    category_slug = category_slug.strip()
    if len(title) < 3 or len(title) > 160:
        raise HTTPException(400, "Informe um título entre 3 e 160 caracteres")
    if len(description) < 5 or len(description) > 10000:
        raise HTTPException(400, "Informe uma descrição válida")
    if price < 0:
        raise HTTPException(400, "Preço inválido")
    if not city or len(state) != 2:
        raise HTTPException(400, "Informe cidade e UF válidas")
    payment_mode = str(payment_mode or "cash").strip().lower()
    if payment_mode not in {"cash", "installments"}:
        raise HTTPException(400, "Forma de venda inválida")
    if original_price is not None and original_price <= price:
        original_price = None

    # Validate plan/category BEFORE writing any image to disk or Supabase Storage.
    with conn() as db:
        access_data = get_publish_plan_access(db, user["id"])
        if not access_data.get("ready"):
            if access_data.get("status") == "quota_full" and access_data.get("plan"):
                quota_plan = access_data["plan"]
                quota_action = " Exclua um anúncio antigo para liberar uma vaga."
                if int(quota_plan.get("boost") or 0) < 3:
                    quota_action = " Exclua um anúncio antigo para liberar uma vaga ou faça upgrade para um plano maior."
                raise HTTPException(
                    403,
                    f"Você atingiu o limite de {access_data.get('ad_limit', 0)} anúncios do plano {quota_plan.get('name', '')}.{quota_action}",
                )
            if access_data.get("status") == "expired" and access_data.get("plan"):
                expired_code = access_data["plan"].get("code")
                if expired_code == "boost_30":
                    raise HTTPException(403, "Seu Premium venceu. Renove o Premium para voltar a publicar.")
                if expired_code == "boost_15":
                    raise HTTPException(403, "Seu Plus venceu. Renove o Plus ou faça upgrade para Premium para voltar a publicar.")
            raise HTTPException(403, "Escolha um plano antes de publicar o anúncio")
        selected_plan = access_data.get("plan")
        if not selected_plan:
            raise HTTPException(403, "O plano selecionado não está mais disponível")
        if not db.execute("SELECT 1 FROM categories WHERE slug=?", (category_slug,)).fetchone():
            raise HTTPException(400, "Categoria inválida")
        if selected_plan.get("code") == "boost_7":
            if db.execute("SELECT 1 FROM free_plan_usage WHERE user_id=?", (user["id"],)).fetchone():
                raise HTTPException(403, "O Plano Grátis já foi utilizado nesta conta. Escolha Plus ou Premium.")
            if REQUIRE_EMAIL_VERIFICATION_FOR_FREE and not bool(user.get("email_verified")):
                raise HTTPException(403, "Confirme seu e-mail antes de utilizar o Plano Grátis.")

    gallery_files = [img for img in (images or []) if getattr(img, "filename", None)]
    if image and image.filename:
        gallery_files.insert(0, image)
    if len(gallery_files) > 8:
        raise HTTPException(400, "Envie no máximo 8 imagens por anúncio")
    gallery_urls = []
    try:
        for img in gallery_files:
            gallery_urls.append(await save_product_image(img))
        image_url = gallery_urls[0] if gallery_urls else None
        pid = str(uuid.uuid4())
        with conn() as db:
            # Revalida plano e cota o mais perto possível da gravação. Isso
            # protege contra duas publicações simultâneas consumindo a mesma vaga.
            if USE_POSTGRES:
                db.execute("SELECT id FROM users WHERE id=? FOR UPDATE", (user["id"],)).fetchone()
            access_data = get_publish_plan_access(db, user["id"])
            if not access_data.get("ready"):
                if access_data.get("status") == "quota_full" and access_data.get("plan"):
                    quota_plan = access_data["plan"]
                    quota_action = " Exclua um anúncio antigo para liberar uma vaga."
                    if int(quota_plan.get("boost") or 0) < 3:
                        quota_action = " Exclua um anúncio antigo para liberar uma vaga ou faça upgrade para um plano maior."
                    raise HTTPException(
                        409,
                        f"Limite de {access_data.get('ad_limit', 0)} anúncios do plano {quota_plan.get('name', '')} atingido.{quota_action}",
                    )
                if access_data.get("status") == "expired" and access_data.get("plan"):
                    expired_code = access_data["plan"].get("code")
                    if expired_code == "boost_30":
                        raise HTTPException(409, "Seu Premium venceu. Renove o Premium para voltar a publicar.")
                    if expired_code == "boost_15":
                        raise HTTPException(409, "Seu Plus venceu. Renove o Plus ou faça upgrade para Premium para voltar a publicar.")
                raise HTTPException(409, "Seu plano não está mais disponível para nova publicação. Atualize a página e tente novamente.")
            selected_plan = access_data.get("plan")
            if not selected_plan:
                raise HTTPException(409, "Plano indisponível")
            created_at = now_iso()
            boost_level = int(selected_plan.get("boost") or 0)
            is_featured = 1 if boost_level > 0 else 0
            plan_days = max(0, int(selected_plan.get("days") or 0))
            # Se o usuário já tem um plano de conta ativo, novos anúncios usam
            # o mesmo vencimento. Uma compra ainda não iniciada começa no
            # primeiro anúncio publicado.
            plan_expires_at = access_data.get("expires_at")
            if not plan_expires_at:
                plan_expires_at = (now_dt() + timedelta(days=plan_days)).isoformat() if plan_days else None
            featured_until = plan_expires_at if is_featured else None
            db.execute(
                """INSERT INTO products(id,seller_id,title,description,price,category_slug,city,state,neighborhood,condition,image_url,image_urls,original_price,payment_mode,status,featured,featured_until,boost_level,plan_code,plan_expires_at,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, user["id"], title, description, price, category_slug, city, state, neighborhood.strip(), condition, image_url, json.dumps(gallery_urls), original_price, payment_mode, "active", is_featured, featured_until, boost_level, selected_plan.get("code"), plan_expires_at, created_at, created_at),
            )
            if selected_plan.get("code") == "boost_7":
                db.execute(
                    """INSERT INTO free_plan_usage(user_id,product_id,used_at) VALUES (?,?,?)
                       ON CONFLICT(user_id) DO NOTHING""",
                    (user["id"], pid, created_at),
                )
            if access_data.get("entitlement_id"):
                db.execute(
                    "UPDATE publish_entitlements SET status='used',product_id=?,updated_at=? WHERE id=? AND status='ready'",
                    (pid, created_at, access_data["entitlement_id"]),
                )
                # Legacy mirror keeps old clients consistent with the consumed entitlement.
                db.execute("UPDATE publish_plan_access SET status='used',product_id=?,updated_at=? WHERE user_id=?", (pid, created_at, user["id"]))
            if not selected_plan.get("free") and plan_expires_at:
                activate_account_plan_entitlement(
                    db,
                    user["id"],
                    selected_plan.get("code"),
                    plan_expires_at,
                    access_data.get("payment_order_id"),
                    pid,
                )
            if access_data.get("payment_order_id"):
                db.execute("UPDATE payment_orders SET product_id=? WHERE id=?", (pid, access_data["payment_order_id"]))
            db.execute(
                "INSERT INTO notifications(id,type,product_id,title,body,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), "new_product", pid, "Novo anúncio publicado", f"{title} • {city} - {state}", created_at),
            )
            db.commit()
        return {"id": pid, "plan_code": selected_plan.get("code")}
    except Exception:
        delete_product_images(gallery_urls)
        raise


@app.put("/api/products/{product_id}")
def update_product(product_id: str, payload: dict, user=Depends(current_user)):
    allowed = {"title", "description", "price", "category_slug", "city", "state", "neighborhood", "condition", "status", "original_price", "payment_mode"}
    fields = [(k, payload[k]) for k in payload if k in allowed]
    if not fields:
        raise HTTPException(400, "Nenhum campo válido")
    if "status" in payload and payload["status"] not in {"active", "sold", "paused"}:
        raise HTTPException(400, "Status inválido")
    if "payment_mode" in payload and payload["payment_mode"] not in {"cash", "installments"}:
        raise HTTPException(400, "Forma de venda inválida")
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode editar este anúncio")
        row_data = dict(row)
        if payload.get("status") == "active" and row_data.get("plan_code") == "boost_7" and row_data.get("plan_expires_at"):
            try:
                if datetime.fromisoformat(row_data["plan_expires_at"]) <= now_dt() and user["role"] != "admin":
                    raise HTTPException(403, "Seu anúncio grátis venceu. Faça upgrade para Plus ou Premium para reativá-lo.")
            except ValueError:
                pass
        payload_price = payload.get("price", row["price"])
        if any(k == "original_price" for k, _ in fields):
            original_price = payload.get("original_price")
            if original_price is not None and original_price != "" and float(original_price) <= float(payload_price):
                fields = [(k, (None if k == "original_price" else v)) for k, v in fields]
        fields.append(("updated_at", now_iso()))
        sql = ", ".join(f"{k}=?" for k, _ in fields)
        db.execute(f"UPDATE products SET {sql} WHERE id=?", (*[v for _, v in fields], product_id))
        db.commit()
    return {"ok": True}


@app.post("/api/products/{product_id}/image")
async def replace_product_image(product_id: str, image: UploadFile = File(...), user=Depends(current_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode editar este anúncio")
        old_images = normalize_product_images(dict(row))

    image_url = await save_product_image(image)
    try:
        with conn() as db:
            db.execute("UPDATE products SET image_url=?,image_urls=?,updated_at=? WHERE id=?", (image_url, json.dumps([image_url]), now_iso(), product_id))
            db.commit()
    except Exception:
        delete_product_image(image_url)
        raise
    delete_product_images(old_images)
    return {"ok": True, "image_url": image_url, "images": [image_url]}


@app.post("/api/products/{product_id}/gallery")
async def replace_product_gallery(product_id: str, images: list[UploadFile] = File(...), user=Depends(current_user)):
    files = [img for img in (images or []) if getattr(img, "filename", None)]
    if not files:
        raise HTTPException(400, "Envie pelo menos uma imagem")
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode editar este anúncio")
        old_images = normalize_product_images(dict(row))
    gallery_urls = []
    try:
        for img in files[:8]:
            gallery_urls.append(await save_product_image(img))
        with conn() as db:
            db.execute("UPDATE products SET image_url=?,image_urls=?,updated_at=? WHERE id=?", (gallery_urls[0], json.dumps(gallery_urls), now_iso(), product_id))
            db.commit()
    except Exception:
        delete_product_images(gallery_urls)
        raise
    delete_product_images(old_images)
    return {"ok": True, "image_url": gallery_urls[0], "images": gallery_urls}


@app.post("/api/products/{product_id}/gallery/add")
async def add_product_gallery_images(product_id: str, images: list[UploadFile] = File(...), user=Depends(current_user)):
    files = [img for img in (images or []) if getattr(img, "filename", None)]
    if not files:
        raise HTTPException(400, "Envie pelo menos uma imagem")
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode editar este anúncio")
        gallery_urls = normalize_product_images(dict(row))
    available = max(0, 8 - len(gallery_urls))
    if available <= 0:
        raise HTTPException(400, "A galeria já atingiu o limite de 8 imagens")
    existing_count = len(gallery_urls)
    try:
        for img in files[:available]:
            gallery_urls.append(await save_product_image(img))
        with conn() as db:
            primary = gallery_urls[0] if gallery_urls else None
            db.execute("UPDATE products SET image_url=?,image_urls=?,updated_at=? WHERE id=?", (primary, json.dumps(gallery_urls), now_iso(), product_id))
            db.commit()
    except Exception:
        delete_product_images(gallery_urls[existing_count:])
        raise
    return {"ok": True, "image_url": gallery_urls[0], "images": gallery_urls}


class PaymentIntegrationIn(BaseModel):
    enabled: bool = False
    is_default: bool = False
    mode: str = "sandbox"
    credentials: dict[str, str] = Field(default_factory=dict)


class GalleryOrderIn(BaseModel):
    images: list[str]


@app.put("/api/products/{product_id}/gallery/order")
def reorder_product_gallery(product_id: str, payload: GalleryOrderIn, user=Depends(current_user)):
    ordered = [u for u in payload.images if isinstance(u, str) and u.strip()]
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode editar este anúncio")
        current = normalize_product_images(dict(row))
        current_set = set(current)
        filtered = [u for u in ordered if u in current_set]
        missing = [u for u in current if u not in filtered]
        final_images = (filtered + missing)[:8]
        primary = final_images[0] if final_images else None
        db.execute("UPDATE products SET image_url=?,image_urls=?,updated_at=? WHERE id=?", (primary, json.dumps(final_images), now_iso(), product_id))
        db.commit()
    return {"ok": True, "image_url": primary, "images": final_images}


class GalleryRemoveIn(BaseModel):
    image_url: str


@app.delete("/api/products/{product_id}/gallery/image")
def remove_product_gallery_image(product_id: str, payload: GalleryRemoveIn, user=Depends(current_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode editar este anúncio")
        current = normalize_product_images(dict(row))
        if payload.image_url not in current:
            raise HTTPException(404, "Imagem não encontrada na galeria")
        if len(current) <= 1:
            raise HTTPException(400, "O anúncio precisa ter pelo menos uma imagem")
        final_images = [u for u in current if u != payload.image_url]
        primary = final_images[0] if final_images else None
        db.execute("UPDATE products SET image_url=?,image_urls=?,updated_at=? WHERE id=?", (primary, json.dumps(final_images), now_iso(), product_id))
        db.commit()
    delete_product_image(payload.image_url)
    return {"ok": True, "image_url": primary, "images": final_images}


@app.delete("/api/products/{product_id}")
def delete_product(product_id: str, user=Depends(current_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode excluir este anúncio")
        delete_product_images(normalize_product_images(dict(row)))
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
        db.commit()
    return {"ok": True}


@app.get("/api/me/products")
def my_products(user=Depends(current_user)):
    with conn() as db:
        cleanup_expired_features(db)
        db.commit()
        rows = db.execute("SELECT * FROM products WHERE seller_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        return products_to_dicts(db, rows, user["id"])


@app.get("/api/me/dashboard")
def my_dashboard(user=Depends(current_user)):
    with conn() as db:
        cleanup_expired_features(db)
        db.commit()
        row = db.execute(
            """SELECT COUNT(*) total,
               SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) active,
               SUM(CASE WHEN status='sold' THEN 1 ELSE 0 END) sold,
               COALESCE(SUM(views),0) views
               FROM products WHERE seller_id=?""", (user["id"],)
        ).fetchone()
        favs = db.execute("SELECT COUNT(*) n FROM favorites f JOIN products p ON p.id=f.product_id WHERE p.seller_id=?", (user["id"],)).fetchone()["n"]
        unread = db.execute(
            """SELECT COUNT(*) n FROM messages m JOIN conversations c ON c.id=m.conversation_id
               WHERE (c.buyer_id=? OR c.seller_id=?) AND m.sender_id<>? AND m.read_at IS NULL""",
            (user["id"], user["id"], user["id"]),
        ).fetchone()["n"]
        featured_rows = db.execute(
            """SELECT id,title,price,featured_until,boost_level,status,image_url,city,state
               FROM products
               WHERE seller_id=? AND featured=1 AND featured_until IS NOT NULL AND featured_until>?
               ORDER BY boost_level DESC, featured_until ASC""",
            (user["id"], now_iso()),
        ).fetchall()
        publish_access = get_publish_plan_access(db, user["id"])
    featured_ads = []
    highest_boost = 0
    next_expiration = None
    for r in featured_rows:
        data = dict(r)
        meta = plan_meta_from_boost(data.get("boost_level")) or {}
        highest_boost = max(highest_boost, int(data.get("boost_level") or 0))
        exp = data.get("featured_until")
        if exp and (next_expiration is None or exp < next_expiration):
            next_expiration = exp
        days_left = None
        expiring_soon = False
        if exp:
            try:
                expires_dt = datetime.fromisoformat(exp)
                delta = expires_dt - now_dt()
                days_left = max(0, delta.days + (1 if delta.seconds > 0 else 0))
                expiring_soon = delta <= timedelta(days=3)
            except Exception:
                pass
        featured_ads.append({
            "id": data["id"],
            "title": data["title"],
            "price": data["price"],
            "image_url": data.get("image_url"),
            "city": data.get("city"),
            "state": data.get("state"),
            "featured_until": exp,
            "days_left": days_left,
            "expiring_soon": expiring_soon,
            "boost_level": data.get("boost_level") or 0,
            "plan_name": meta.get("name"),
            "plan_code": meta.get("code"),
        })
    current_meta = publish_access.get("plan") or plan_meta_from_boost(highest_boost) or {"name": "Grátis", "code": "boost_7"}
    access_expiration = publish_access.get("expires_at")
    if access_expiration:
        next_expiration = access_expiration
    return {
        "total": row["total"] or 0,
        "active": row["active"] or 0,
        "sold": row["sold"] or 0,
        "views": row["views"] or 0,
        "favorites_received": favs,
        "unread_messages": unread,
        "plan_summary": {
            "featured_count": len(featured_ads),
            "current_plan_name": current_meta.get("name", "Grátis"),
            "current_plan_code": current_meta.get("code"),
            "next_expiration": next_expiration,
            "ad_limit": int(publish_access.get("ad_limit") or current_meta.get("ad_limit") or 0),
            "ads_used": int(publish_access.get("ads_used") or 0),
            "ads_remaining": int(publish_access.get("ads_remaining") or 0),
            "quota_status": publish_access.get("status"),
            "featured_ads": featured_ads,
            "expiring_soon_count": sum(1 for item in featured_ads if item.get("expiring_soon")),
        },
    }


@app.get("/api/me/notifications")
def my_notifications(limit: int = 20, user=Depends(current_user)):
    safe_limit = max(1, min(int(limit or 20), 50))
    with conn() as db:
        rows = db.execute(
            """SELECT n.*, CASE WHEN r.notification_id IS NULL THEN 1 ELSE 0 END unread
               FROM notifications n
               LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.user_id=?
               LEFT JOIN products p ON p.id=n.product_id
               WHERE n.target_user_id=?
                  OR (n.target_user_id IS NULL AND (n.product_id IS NULL OR p.seller_id<>?))
               ORDER BY n.created_at DESC
               LIMIT ?""",
            (user["id"], user["id"], user["id"], safe_limit),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/me/notifications/unread-count")
def unread_notifications_count(user=Depends(current_user)):
    with conn() as db:
        row = db.execute(
            """SELECT COUNT(*) n
               FROM notifications n
               LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.user_id=?
               LEFT JOIN products p ON p.id=n.product_id
               WHERE r.notification_id IS NULL
                 AND (n.target_user_id=?
                      OR (n.target_user_id IS NULL AND (n.product_id IS NULL OR p.seller_id<>?)))""",
            (user["id"], user["id"], user["id"]),
        ).fetchone()
    return {"count": row["n"] if row else 0}


@app.post("/api/me/notifications/{notification_id}/read")
def read_notification(notification_id: str, user=Depends(current_user)):
    with conn() as db:
        n = db.execute(
            """SELECT n.*, p.seller_id product_seller_id
               FROM notifications n
               LEFT JOIN products p ON p.id=n.product_id
               WHERE n.id=?""",
            (notification_id,),
        ).fetchone()
        if not n:
            raise HTTPException(404, "Notificação não encontrada")
        data = dict(n)
        allowed = data.get("target_user_id") == user["id"] or (
            data.get("target_user_id") is None and (data.get("product_id") is None or data.get("product_seller_id") != user["id"])
        )
        if not allowed:
            raise HTTPException(404, "Notificação não encontrada")
        db.execute(
            "INSERT OR IGNORE INTO notification_reads(notification_id,user_id,read_at) VALUES (?,?,?)",
            (notification_id, user["id"], now_iso()),
        )
        db.commit()
    return {"ok": True}


@app.post("/api/me/notifications/read-all")
def read_all_notifications(user=Depends(current_user)):
    with conn() as db:
        rows = db.execute(
            """SELECT n.id FROM notifications n
               LEFT JOIN products p ON p.id=n.product_id
               WHERE n.target_user_id=?
                  OR (n.target_user_id IS NULL AND (n.product_id IS NULL OR p.seller_id<>?))""",
            (user["id"], user["id"]),
        ).fetchall()
        now = now_iso()
        for row in rows:
            db.execute(
                "INSERT OR IGNORE INTO notification_reads(notification_id,user_id,read_at) VALUES (?,?,?)",
                (row["id"], user["id"], now),
            )
        db.commit()
    return {"ok": True}


@app.post("/api/products/{product_id}/favorite")
def toggle_favorite(product_id: str, user=Depends(current_user)):
    with conn() as db:
        if not db.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone():
            raise HTTPException(404, "Anúncio não encontrado")
        exists = db.execute("SELECT 1 FROM favorites WHERE user_id=? AND product_id=?", (user["id"], product_id)).fetchone()
        if exists:
            db.execute("DELETE FROM favorites WHERE user_id=? AND product_id=?", (user["id"], product_id))
            favorite = False
        else:
            db.execute("INSERT INTO favorites(user_id,product_id) VALUES (?,?)", (user["id"], product_id))
            favorite = True
        db.commit()
    return {"favorite": favorite}


@app.get("/api/me/favorites")
def favorites(user=Depends(current_user)):
    with conn() as db:
        rows = db.execute("""SELECT p.* FROM products p JOIN favorites f ON f.product_id=p.id
                           WHERE f.user_id=? ORDER BY p.created_at DESC""", (user["id"],)).fetchall()
        return products_to_dicts(db, rows, user["id"])


# Chat -----------------------------------------------------------------------
@app.post("/api/products/{product_id}/conversation")
def start_conversation(product_id: str, user=Depends(current_user)):
    with conn() as db:
        p = db.execute("SELECT * FROM products WHERE id=? AND status='active'", (product_id,)).fetchone()
        if not p:
            raise HTTPException(404, "Anúncio não encontrado")
        if p["seller_id"] == user["id"]:
            raise HTTPException(400, "Este anúncio é seu")
        c = db.execute("SELECT * FROM conversations WHERE product_id=? AND buyer_id=? AND seller_id=?", (product_id, user["id"], p["seller_id"])).fetchone()
        if not c:
            cid = str(uuid.uuid4())
            db.execute("INSERT INTO conversations(id,product_id,buyer_id,seller_id,created_at,updated_at) VALUES (?,?,?,?,?,?)", (cid, product_id, user["id"], p["seller_id"], now_iso(), now_iso()))
        else:
            cid = c["id"]
        db.execute("DELETE FROM hidden_conversations WHERE conversation_id=? AND user_id=?", (cid, user["id"]))
        db.commit()
    return {"conversation_id": cid}


def conversation_dict(db, row, me_id):
    data = dict(row)
    p = db.execute("SELECT id,title,price,image_url,status FROM products WHERE id=?", (row["product_id"],)).fetchone()
    other_id = row["seller_id"] if row["buyer_id"] == me_id else row["buyer_id"]
    other = db.execute("SELECT id,name,verified FROM users WHERE id=?", (other_id,)).fetchone()
    last = db.execute("SELECT body,created_at,sender_id FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT 1", (row["id"],)).fetchone()
    unread = db.execute("SELECT COUNT(*) n FROM messages WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL", (row["id"], me_id)).fetchone()["n"]
    data["product"] = dict(p) if p else None
    data["other_user"] = dict(other) if other else None
    if data["other_user"]:
        data["other_user"]["verified"] = bool(data["other_user"]["verified"])
    data["last_message"] = dict(last) if last else None
    data["unread"] = unread
    data["is_seller"] = row["seller_id"] == me_id
    data["updated_at"] = row["updated_at"]
    return data


@app.get("/api/me/conversations")
def my_conversations(user=Depends(current_user)):
    with conn() as db:
        rows = db.execute(
            """SELECT * FROM conversations
               WHERE (buyer_id=? OR seller_id=?)
                 AND id NOT IN (SELECT conversation_id FROM hidden_conversations WHERE user_id=?)
               ORDER BY updated_at DESC""",
            (user["id"], user["id"], user["id"]),
        ).fetchall()
        return [conversation_dict(db, r, user["id"]) for r in rows]


@app.delete("/api/conversations/{conversation_id}")
def hide_conversation(conversation_id: str, user=Depends(current_user)):
    with conn() as db:
        c = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not c or user["id"] not in {c["buyer_id"], c["seller_id"]}:
            raise HTTPException(404, "Conversa não encontrada")
        db.execute(
            """INSERT INTO hidden_conversations(user_id,conversation_id,hidden_at) VALUES (?,?,?)
               ON CONFLICT(user_id,conversation_id) DO UPDATE SET hidden_at=excluded.hidden_at""",
            (user["id"], conversation_id, now_iso()),
        )
        db.execute(
            "UPDATE messages SET read_at=COALESCE(read_at, ?) WHERE conversation_id=? AND sender_id<>?",
            (now_iso(), conversation_id, user["id"]),
        )
        db.commit()
    return {"ok": True}


@app.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str, user=Depends(current_user)):
    with conn() as db:
        c = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not c or user["id"] not in {c["buyer_id"], c["seller_id"]}:
            raise HTTPException(404, "Conversa não encontrada")
        read_at = now_iso()
        db.execute("UPDATE messages SET read_at=? WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL", (read_at, conversation_id, user["id"]))
        pending_notifications = db.execute(
            """SELECT n.id FROM notifications n
               LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.user_id=?
               WHERE n.type='chat_message' AND n.conversation_id=? AND n.target_user_id=? AND r.notification_id IS NULL""",
            (user["id"], conversation_id, user["id"]),
        ).fetchall()
        for n in pending_notifications:
            db.execute(
                "INSERT OR IGNORE INTO notification_reads(notification_id,user_id,read_at) VALUES (?,?,?)",
                (n["id"], user["id"], read_at),
            )
        rows = db.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC", (conversation_id,)).fetchall()
        db.commit()
    return [dict(r) for r in rows]


@app.post("/api/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, payload: MessageIn, user=Depends(current_user)):
    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "Mensagem vazia")
    if len(body) > 2000:
        raise HTTPException(400, "Mensagem muito longa")
    with conn() as db:
        c = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not c or user["id"] not in {c["buyer_id"], c["seller_id"]}:
            raise HTTPException(404, "Conversa não encontrada")
        created_at = now_iso()
        mid = str(uuid.uuid4())
        db.execute("INSERT INTO messages(id,conversation_id,sender_id,body,created_at) VALUES (?,?,?,?,?)", (mid, conversation_id, user["id"], body, created_at))
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (created_at, conversation_id))

        recipient_id = c["seller_id"] if user["id"] == c["buyer_id"] else c["buyer_id"]
        db.execute("DELETE FROM hidden_conversations WHERE conversation_id=? AND user_id IN (?,?)", (conversation_id, user["id"], recipient_id))
        product = db.execute("SELECT id,title FROM products WHERE id=?", (c["product_id"],)).fetchone()
        sender = db.execute("SELECT name FROM users WHERE id=?", (user["id"],)).fetchone()
        product_title = product["title"] if product else "anúncio"
        sender_name = sender["name"] if sender and sender["name"] else "Usuário"
        preview = body if len(body) <= 90 else body[:87] + "..."
        db.execute(
            """INSERT INTO notifications(id,type,product_id,title,body,created_at,target_user_id,conversation_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), "chat_message", c["product_id"], "Nova mensagem no chat", f"{sender_name} • {product_title}: {preview}", created_at, recipient_id, conversation_id),
        )
        db.commit()
    return {"id": mid}


# Reports --------------------------------------------------------------------
@app.post("/api/products/{product_id}/report")
def report_product(product_id: str, payload: ReportIn, user=Depends(current_user)):
    with conn() as db:
        if not db.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone():
            raise HTTPException(404, "Anúncio não encontrado")
        if db.execute("SELECT 1 FROM reports WHERE reporter_id=? AND product_id=? AND status='open'", (user["id"], product_id)).fetchone():
            raise HTTPException(409, "Você já possui uma denúncia aberta para este anúncio")
        rid = str(uuid.uuid4())
        db.execute("INSERT INTO reports(id,reporter_id,product_id,reason,details,status,created_at) VALUES (?,?,?,?,?,'open',?)", (rid, user["id"], product_id, payload.reason.strip()[:120], payload.details.strip()[:2000], now_iso()))
        db.commit()
    return {"id": rid, "ok": True}


# Plans / payments -----------------------------------------------------------

def _digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _valid_cpf(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    nums = [int(x) for x in cpf]
    for size in (9, 10):
        total = sum(nums[i] * (size + 1 - i) for i in range(size))
        digit = (total * 10 % 11) % 10
        if digit != nums[size]:
            return False
    return True

def _valid_cnpj(cnpj: str) -> bool:
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    nums = [int(x) for x in cnpj]
    weights1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    weights2 = [6,5,4,3,2,9,8,7,6,5,4,3,2]
    def digit(values, weights):
        rem = sum(v*w for v,w in zip(values, weights)) % 11
        return 0 if rem < 2 else 11-rem
    d1 = digit(nums[:12], weights1)
    d2 = digit(nums[:12] + [d1], weights2)
    return nums[12] == d1 and nums[13] == d2

def _validate_tax_id(value: str | None) -> str:
    tax_id = _digits(value)
    if not ((_valid_cpf(tax_id) if len(tax_id) == 11 else False) or (_valid_cnpj(tax_id) if len(tax_id) == 14 else False)):
        raise HTTPException(400, "Informe um CPF ou CNPJ válido para gerar o PIX PagBank")
    return tax_id


def _pagbank_base_url(mode: str) -> str:
    return "https://api.pagseguro.com" if mode == "production" else "https://sandbox.api.pagseguro.com"


def _pagbank_config(db, require_enabled: bool = True):
    row = db.execute("SELECT * FROM payment_integrations WHERE provider='pagbank' LIMIT 1").fetchone()
    if not row:
        return None
    if require_enabled and not bool(row["enabled"]):
        return None
    data = dict(row)
    credentials = decrypt_payment_credentials(data.get("credentials_enc"))
    token = str(credentials.get("token") or "").strip()
    if not token:
        return None
    return {"mode": data.get("mode") or "sandbox", "token": token, "row": data}


def _pagbank_headers(token: str, idempotency_key: str | None = None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["x-idempotency-key"] = "".join(ch for ch in idempotency_key if ch.isalnum())[:200]
    return headers


def _pagbank_customer(user: dict, tax_id: str):
    customer = {
        "name": str(user.get("name") or "Cliente ClassificaJa")[:120],
        "email": str(user.get("email") or "")[:255],
        "tax_id": tax_id,
    }
    phone = _digits(user.get("phone"))
    if phone.startswith("55") and len(phone) >= 12:
        phone = phone[2:]
    if len(phone) in {10, 11}:
        customer["phones"] = [{
            "country": "55",
            "area": phone[:2],
            "number": phone[2:],
            "type": "MOBILE",
        }]
    return customer


def _activate_paid_order(db, order):
    order_data = dict(order)
    if order_data.get("status") == "paid":
        return
    plan = get_plan(order_data.get("plan_code"), db, include_inactive=True)
    if order_data.get("plan_code") == "boost_7" and float(order_data.get("amount") or 0) > 0:
        plan = {"name": "Básico legado 7 dias", "amount": float(order_data.get("amount") or 0), "days": 7, "boost": 1}
    paid_at = now_iso()
    db.execute("UPDATE payment_orders SET status='paid',paid_at=? WHERE id=?", (paid_at, order_data["id"]))

    if not plan:
        return

    user_id = order_data["user_id"]
    plan_code = order_data.get("plan_code")
    plan_days = max(0, int(plan.get("days") or 0))
    target_boost = int(plan.get("boost") or 0)

    if order_data.get("product_id"):
        product = db.execute("SELECT featured_until FROM products WHERE id=?", (order_data["product_id"],)).fetchone()
        base_dt = now_dt()
        if product and product["featured_until"]:
            try:
                current_until = datetime.fromisoformat(product["featured_until"])
                if current_until > base_dt:
                    base_dt = current_until
            except Exception:
                pass
        until = (base_dt + timedelta(days=plan_days)).isoformat()
        db.execute(
            "UPDATE products SET featured=1,featured_until=?,boost_level=?,plan_code=?,plan_expires_at=?,status='active',updated_at=? WHERE id=?",
            (until, target_boost, plan_code, until, now_iso(), order_data["product_id"]),
        )
        if plan_code in {"boost_15", "boost_30"}:
            # O pagamento renova/eleva o plano da conta, não apenas um anúncio.
            db.execute(
                "UPDATE publish_entitlements SET status='consumed',updated_at=? WHERE user_id=? AND status='ready' AND plan_code IN ('boost_15','boost_30')",
                (now_iso(), user_id),
            )
            activate_account_plan_entitlement(
                db,
                user_id,
                plan_code,
                until,
                order_data.get("id"),
                order_data.get("product_id"),
            )
            # Todos os anúncios ativos da conta acompanham o plano da conta.
            db.execute(
                """UPDATE products
                   SET featured=CASE WHEN status='active' THEN 1 ELSE featured END,
                       featured_until=CASE WHEN status='active' THEN ? ELSE featured_until END,
                       boost_level=CASE WHEN status='active' THEN ? ELSE boost_level END,
                       plan_code=?,plan_expires_at=?,updated_at=?
                   WHERE seller_id=?""",
                (until, target_boost, plan_code, until, now_iso(), user_id),
            )
    elif plan_code in {"boost_15", "boost_30"}:
        # Compra/renovação feita pela página de planos da conta. O período começa
        # na confirmação do pagamento. Na renovação/upgrade preservamos o tempo
        # restante: os novos dias são somados ao vencimento atual, quando houver.
        access = get_publish_plan_access(db, user_id)
        base_dt = now_dt()
        current_exp = _parse_iso_dt(access.get("expires_at"))
        if current_exp and current_exp > base_dt:
            base_dt = current_exp
        until = (base_dt + timedelta(days=plan_days)).isoformat()
        db.execute(
            "UPDATE publish_entitlements SET status='consumed',updated_at=? WHERE user_id=? AND status='ready' AND plan_code IN ('boost_15','boost_30')",
            (now_iso(), user_id),
        )
        activate_account_plan_entitlement(db, user_id, plan_code, until, order_data.get("id"), None)
        db.execute(
            """UPDATE products
               SET featured=CASE WHEN status='active' THEN 1 ELSE featured END,
                   featured_until=CASE WHEN status='active' THEN ? ELSE featured_until END,
                   boost_level=CASE WHEN status='active' THEN ? ELSE boost_level END,
                   plan_code=?,plan_expires_at=?,updated_at=?
               WHERE seller_id=?""",
            (until, target_boost, plan_code, until, now_iso(), user_id),
        )
        db.execute(
            """INSERT INTO publish_plan_access(user_id,plan_code,status,payment_order_id,product_id,selected_at,updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET plan_code=excluded.plan_code,status=excluded.status,
                 payment_order_id=excluded.payment_order_id,product_id=excluded.product_id,
                 selected_at=excluded.selected_at,updated_at=excluded.updated_at""",
            (user_id, plan_code, "active", order_data.get("id"), None, paid_at, paid_at),
        )
    else:
        # Compatibilidade com planos legados/grátis pagos antigos.
        set_publish_plan_access(db, user_id, plan_code, "ready", order_data.get("id"), None)


def _update_pagbank_order_from_payload(db, order, payload: dict):
    order_data = dict(order)
    charges = payload.get("charges") or []
    charge = charges[0] if charges else payload if str(payload.get("id") or "").startswith("CHAR_") else {}
    status = str(charge.get("status") or "").upper()
    if status == "PAID":
        _activate_paid_order(db, order_data)
    elif status == "CANCELED":
        db.execute("UPDATE payment_orders SET status='cancelled' WHERE id=? AND status<>'paid'", (order_data["id"],))
    elif status == "DECLINED":
        db.execute("UPDATE payment_orders SET status='failed' WHERE id=? AND status<>'paid'", (order_data["id"],))
    elif status in {"WAITING", "AUTHORIZED", "IN_ANALYSIS"}:
        db.execute("UPDATE payment_orders SET status='pending' WHERE id=? AND status<>'paid'", (order_data["id"],))


def _create_pagbank_pix(order_id: str, user: dict, plan: dict, tax_id: str, request: Request, config: dict):
    import httpx
    amount_cents = int(round(float(plan.get("amount") or 0) * 100))
    if amount_cents <= 0:
        raise HTTPException(400, "Valor inválido para cobrança PagBank")
    expiration = (now_dt() + timedelta(minutes=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    base_public = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    webhook_url = f"{base_public}/api/webhooks/pagbank"
    reference = f"CJ-{order_id}"
    payload = {
        "reference_id": reference[:64],
        "customer": _pagbank_customer(user, tax_id),
        "items": [{
            "reference_id": str(plan.get("code") or "plano")[:255],
            "name": str(plan.get("name") or "Plano ClassificaJa")[:200],
            "quantity": 1,
            "unit_amount": amount_cents,
        }],
        "charges": [{
            "reference_id": order_id[:64],
            "description": f"ClassificaJa - {str(plan.get('name') or 'Plano')}"[:64],
            "amount": {"value": amount_cents, "currency": "BRL"},
            "payment_method": {"type": "PIX", "pix": {"expiration_date": expiration}},
        }],
        "notification_urls": [webhook_url],
    }
    url = f"{_pagbank_base_url(config['mode'])}/orders"
    try:
        response = httpx.post(
            url,
            headers=_pagbank_headers(config["token"], order_id),
            json=payload,
            timeout=30,
        )
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Não foi possível conectar ao PagBank: {exc.__class__.__name__}")
    try:
        data = response.json()
    except Exception:
        data = {}
    if response.status_code >= 300:
        msg = data.get("error_messages") or data.get("message") or data.get("error") or response.text[:300]
        raise HTTPException(502, f"PagBank recusou a criação do PIX: {msg}")
    charges = data.get("charges") or []
    charge = charges[0] if charges else {}
    qr_code = charge.get("qr_code") or {}
    links = charge.get("links") or []
    qr_png = next((link.get("href") for link in links if link.get("rel") == "QRCODE.PNG"), None)
    pix_code = qr_code.get("text")
    if not pix_code:
        raise HTTPException(502, "PagBank não retornou o código PIX")
    safe_payload = {
        "pagbank_order_id": data.get("id"),
        "charge_id": charge.get("id"),
        "charge_status": charge.get("status"),
        "pix_code": pix_code,
        "qr_png_url": qr_png,
        "expiration_date": ((charge.get("payment_method") or {}).get("pix") or {}).get("expiration_date") or expiration,
        "webhook_url": webhook_url,
    }
    return data, safe_payload


def _sync_pagbank_payment(db, order, config: dict):
    import httpx
    order_data = dict(order)
    external_id = order_data.get("external_id")
    if not external_id:
        return order_data.get("status")
    url = f"{_pagbank_base_url(config['mode'])}/orders/{external_id}"
    try:
        response = httpx.get(url, headers=_pagbank_headers(config["token"]), timeout=20)
        if response.status_code < 300:
            payload = response.json()
            _update_pagbank_order_from_payload(db, order_data, payload)
            return (db.execute("SELECT status FROM payment_orders WHERE id=?", (order_data["id"],)).fetchone() or {}).get("status") if USE_POSTGRES else db.execute("SELECT status FROM payment_orders WHERE id=?", (order_data["id"],)).fetchone()["status"]
    except Exception:
        pass
    return order_data.get("status")


@app.get("/api/plans")
def plans():
    with conn() as db:
        return get_plan_catalog(db, include_inactive=False)


@app.get("/api/me/publish-plan")
def my_publish_plan(user=Depends(current_user)):
    with conn() as db:
        return get_publish_plan_access(db, user["id"])


@app.post("/api/payments")
def create_payment(payload: PaymentIn, request: Request, user=Depends(current_user)):
    if payload.method not in {"pix", "card"}:
        raise HTTPException(400, "Forma de pagamento inválida")
    with conn() as db:
        plan = get_plan(payload.plan_code, db, include_inactive=False)
        if not plan:
            raise HTTPException(400, "Plano inválido ou indisponível")

        access = get_publish_plan_access(db, user["id"])
        current_plan = access.get("plan") or {}
        current_code = current_plan.get("code")
        target_code = plan.get("code")
        if current_code == "boost_30" and target_code != "boost_30":
            raise HTTPException(409, "Sua conta já é Premium. Para continuar, renove o Premium; downgrade para Plus ou Grátis não é permitido.")
        if current_code == "boost_15" and target_code not in {"boost_15", "boost_30"}:
            raise HTTPException(409, "Sua conta já é Plus. Renove o Plus ou faça upgrade para Premium.")

        purchase_action = "activation"
        if current_code in {"boost_15", "boost_30"} and target_code == current_code:
            purchase_action = "renewal"
        elif current_code == "boost_15" and target_code == "boost_30":
            purchase_action = "upgrade"

        if plan.get("free") or float(plan.get("amount") or 0) <= 0:
            # Plano Grátis: cortesia de uso único por conta; não cria cobrança.
            if REQUIRE_EMAIL_VERIFICATION_FOR_FREE and not bool(user.get("email_verified")):
                raise HTTPException(403, "Confirme seu e-mail antes de liberar o Plano Grátis.")
            if db.execute("SELECT 1 FROM free_plan_usage WHERE user_id=?", (user["id"],)).fetchone():
                raise HTTPException(403, "O Plano Grátis já foi utilizado nesta conta. Escolha Plus ou Premium para publicar novamente.")
            set_publish_plan_access(db, user["id"], plan["code"], "ready", None, None)
            db.commit()
            return {
                "id": None, "status": "free", "amount": 0.0, "method": None,
                "checkout_mode": "free", "pix_code": None, "installments": None,
                "installment_source": "none", "provider_installment_message": "Plano grátis liberado por 7 dias, sem cobrança",
            }
        product = None
        if payload.product_id:
            product = db.execute("SELECT * FROM products WHERE id=?", (payload.product_id,)).fetchone()
            if not product or product["seller_id"] != user["id"]:
                raise HTTPException(403, "Anúncio inválido")
        oid = str(uuid.uuid4())
        if payload.method == "pix":
            config = _pagbank_config(db)
            if not config:
                raise HTTPException(503, "PIX PagBank ainda não está ativo. Configure e ative o PagBank no Painel Master > Integrações PIX.")
            tax_id = _validate_tax_id(payload.tax_id)
            db.execute(
                """INSERT INTO payment_orders(id,user_id,product_id,plan_code,amount,method,status,created_at,provider,installments,installment_source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (oid, user["id"], payload.product_id, payload.plan_code, plan["amount"], "pix", "pending", now_iso(), "pagbank", 1, "pagbank_pix"),
            )
            db.commit()
            try:
                pagbank_data, safe_payload = _create_pagbank_pix(oid, user, plan, tax_id, request, config)
            except HTTPException as exc:
                with conn() as db2:
                    db2.execute("UPDATE payment_orders SET status='failed',provider_payload=? WHERE id=?", (json.dumps({"error": exc.detail}, ensure_ascii=False), oid))
                    db2.commit()
                raise
            charge = (pagbank_data.get("charges") or [{}])[0]
            with conn() as db2:
                db2.execute(
                    "UPDATE payment_orders SET external_id=?,provider_payment_id=?,provider_payload=? WHERE id=?",
                    (pagbank_data.get("id"), charge.get("id"), json.dumps(safe_payload, ensure_ascii=False), oid),
                )
                db2.commit()
            return {
                "id": oid,
                "status": "pending",
                "amount": plan["amount"],
                "method": "pix",
                "checkout_mode": "pagbank",
                "provider": "pagbank",
                "pix_code": safe_payload.get("pix_code"),
                "qr_image_available": bool(safe_payload.get("qr_png_url")),
                "expiration_date": safe_payload.get("expiration_date"),
                "installments": 1,
                "installment_source": "pagbank_pix",
                "provider_installment_message": "PIX PagBank à vista",
                "purchase_action": purchase_action,
            }
        # Cartão ainda não foi habilitado nesta integração.
        raise HTTPException(503, "Pagamento por cartão ainda não está integrado. Use PIX PagBank.")


@app.get("/api/payments/{payment_id}/status")
def payment_status(payment_id: str, user=Depends(current_user)):
    with conn() as db:
        order = db.execute("SELECT * FROM payment_orders WHERE id=?", (payment_id,)).fetchone()
        if not order or order["user_id"] != user["id"]:
            raise HTTPException(404, "Pagamento não encontrado")
        if order["provider"] == "pagbank" and order["status"] == "pending":
            config = _pagbank_config(db, require_enabled=False)
            if config:
                _sync_pagbank_payment(db, order, config)
                db.commit()
                order = db.execute("SELECT * FROM payment_orders WHERE id=?", (payment_id,)).fetchone()
        return {"id": payment_id, "status": order["status"], "paid_at": order["paid_at"], "provider": order["provider"]}


@app.get("/api/payments/{payment_id}/qrcode")
def payment_qrcode(payment_id: str, user=Depends(current_user)):
    import httpx
    with conn() as db:
        order = db.execute("SELECT * FROM payment_orders WHERE id=?", (payment_id,)).fetchone()
        if not order or order["user_id"] != user["id"]:
            raise HTTPException(404, "Pagamento não encontrado")
        if order["provider"] != "pagbank":
            raise HTTPException(400, "Este pagamento não usa QR Code PagBank")
        config = _pagbank_config(db, require_enabled=False)
        if not config:
            raise HTTPException(503, "Integração PagBank indisponível")
        try:
            provider_payload = json.loads(order["provider_payload"] or "{}")
        except Exception:
            provider_payload = {}
        qr_url = provider_payload.get("qr_png_url")
        if not qr_url:
            raise HTTPException(404, "Imagem do QR Code não disponível")
    try:
        response = httpx.get(qr_url, headers={"Authorization": f"Bearer {config['token']}", "Accept": "image/png"}, timeout=20)
    except httpx.RequestError:
        raise HTTPException(502, "Falha ao carregar QR Code do PagBank")
    if response.status_code >= 300:
        raise HTTPException(502, "PagBank não retornou a imagem do QR Code")
    return {"data_url": "data:image/png;base64," + base64.b64encode(response.content).decode("ascii")}


@app.post("/api/webhooks/pagbank")
async def pagbank_webhook(request: Request):
    raw = await request.body()
    with conn() as db:
        config = _pagbank_config(db, require_enabled=False)
        if not config:
            raise HTTPException(503, "Integração PagBank não configurada")
        received_signature = request.headers.get("x-authenticity-token", "").strip().lower()
        expected_signature = hashlib.sha256(config["token"].encode("utf-8") + b"-" + raw).hexdigest().lower()
        if not received_signature or not secrets.compare_digest(received_signature, expected_signature):
            raise HTTPException(401, "Assinatura do webhook PagBank inválida")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            raise HTTPException(400, "Payload PagBank inválido")
        order = None
        provider_order_id = payload.get("id") if str(payload.get("id") or "").startswith("ORDE_") else None
        charges = payload.get("charges") or []
        charge = charges[0] if charges else payload if str(payload.get("id") or "").startswith("CHAR_") else {}
        charge_id = charge.get("id")
        reference_id = charge.get("reference_id")
        if provider_order_id:
            order = db.execute("SELECT * FROM payment_orders WHERE external_id=? LIMIT 1", (provider_order_id,)).fetchone()
        if not order and charge_id:
            order = db.execute("SELECT * FROM payment_orders WHERE provider_payment_id=? LIMIT 1", (charge_id,)).fetchone()
        if not order and reference_id:
            order = db.execute("SELECT * FROM payment_orders WHERE id=? LIMIT 1", (reference_id,)).fetchone()
        if not order:
            return {"ok": True, "ignored": True}
        _update_pagbank_order_from_payload(db, order, payload)
        db.commit()
    return {"ok": True}


@app.post("/api/payments/{payment_id}/demo-confirm")
def demo_confirm_payment(payment_id: str, user=Depends(current_user)):
    """Mantido somente para pagamentos antigos criados em modo demo."""
    with conn() as db:
        order = db.execute("SELECT * FROM payment_orders WHERE id=?", (payment_id,)).fetchone()
        if not order or order["user_id"] != user["id"]:
            raise HTTPException(404, "Pagamento não encontrado")
        if order["provider"] == "pagbank":
            raise HTTPException(400, "Pagamentos PagBank são confirmados automaticamente pelo banco")
        _activate_paid_order(db, order)
        db.commit()
    return {"ok": True, "status": "paid"}


@app.post("/api/products/{product_id}/cancel-feature")
def cancel_product_feature(product_id: str, user=Depends(current_user)):
    with conn() as db:
        product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(404, "Anúncio não encontrado")
        if product["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode editar este anúncio")
        db.execute("UPDATE products SET featured=0,featured_until=NULL,boost_level=0,updated_at=? WHERE id=?", (now_iso(), product_id))
        db.commit()
    return {"ok": True}


@app.post("/api/products/{product_id}/renew-feature")
def renew_product_feature(product_id: str, payload: RenewPlanIn, request: Request, user=Depends(current_user)):
    if payload.method != "pix":
        raise HTTPException(503, "A renovação real está disponível por PIX PagBank")
    with conn() as db:
        product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product or product["seller_id"] != user["id"]:
            raise HTTPException(404, "Anúncio não encontrado")
        access = get_publish_plan_access(db, user["id"])
        account_plan = access.get("plan") or {}
        plan_code = account_plan.get("code")
        if plan_code not in {"boost_15", "boost_30"}:
            boost_level = int(product["boost_level"] or 0)
            plan_meta = plan_meta_from_boost(boost_level)
            plan_code = (plan_meta or {}).get("code")
        if not plan_code or plan_code == "boost_7":
            raise HTTPException(400, "Este anúncio não possui um plano pago renovável")
        plan = get_plan(plan_code, db, include_inactive=True)
        if not plan or float(plan.get("amount") or 0) <= 0:
            raise HTTPException(400, "Plano indisponível para renovação")
        config = _pagbank_config(db)
        if not config:
            raise HTTPException(503, "PIX PagBank ainda não está ativo no Painel Master")
        tax_id = _validate_tax_id(payload.tax_id)
        oid = str(uuid.uuid4())
        db.execute(
            """INSERT INTO payment_orders(id,user_id,product_id,plan_code,amount,method,status,created_at,provider,installments,installment_source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (oid, user["id"], product_id, plan_code, plan["amount"], "pix", "pending", now_iso(), "pagbank", 1, "pagbank_pix"),
        )
        db.commit()
    try:
        pagbank_data, safe_payload = _create_pagbank_pix(oid, user, plan, tax_id, request, config)
    except HTTPException as exc:
        with conn() as db2:
            db2.execute("UPDATE payment_orders SET status='failed',provider_payload=? WHERE id=?", (json.dumps({"error": exc.detail}, ensure_ascii=False), oid))
            db2.commit()
        raise
    charge = (pagbank_data.get("charges") or [{}])[0]
    with conn() as db2:
        db2.execute(
            "UPDATE payment_orders SET external_id=?,provider_payment_id=?,provider_payload=? WHERE id=?",
            (pagbank_data.get("id"), charge.get("id"), json.dumps(safe_payload, ensure_ascii=False), oid),
        )
        db2.commit()
    return {
        "id": oid, "status": "pending", "amount": plan["amount"], "method": "pix",
        "checkout_mode": "pagbank", "provider": "pagbank", "pix_code": safe_payload.get("pix_code"),
        "qr_image_available": bool(safe_payload.get("qr_png_url")), "expiration_date": safe_payload.get("expiration_date"),
        "plan_name": plan.get("name"), "product_title": product["title"],
    }


@app.get("/api/me/payments")
def my_payments(user=Depends(current_user)):
    with conn() as db:
        rows = db.execute("SELECT * FROM payment_orders WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            plan = get_plan(data.get("plan_code"), db, include_inactive=True) or {}
            product = None
            if data.get("product_id"):
                product = db.execute("SELECT id,title FROM products WHERE id=?", (data["product_id"],)).fetchone()
            if data.get("plan_code") == "boost_7" and float(data.get("amount") or 0) > 0:
                data["plan_name"] = "Básico legado 7 dias"
            else:
                data["plan_name"] = plan.get("name", data.get("plan_code"))
            data["product_title"] = product["title"] if product else "Anúncio removido"
            data["installment_label"] = (
                "1x (PIX)" if data.get("method") == "pix"
                else (f"{data.get('installments')}x" if data.get("installments") else "Definido pelo gateway/banco")
            )
            result.append(data)
    return result


# Admin ----------------------------------------------------------------------
@app.get("/api/admin/stats")
def admin_stats(user=Depends(admin_user)):
    with conn() as db:
        def n(sql, params=()):
            row = db.execute(sql, params).fetchone()
            return row["n"] if row else 0
        stats = {
            "users": n("SELECT COUNT(*) n FROM users"),
            "active_users": n("SELECT COUNT(*) n FROM users WHERE status='active'"),
            "blocked_users": n("SELECT COUNT(*) n FROM users WHERE status<>'active'"),
            "admins": n("SELECT COUNT(*) n FROM users WHERE role='admin'"),
            "products": n("SELECT COUNT(*) n FROM products"),
            "active_products": n("SELECT COUNT(*) n FROM products WHERE status='active'"),
            "paused_products": n("SELECT COUNT(*) n FROM products WHERE status='paused'"),
            "rejected_products": n("SELECT COUNT(*) n FROM products WHERE status='rejected'"),
            "sold_products": n("SELECT COUNT(*) n FROM products WHERE status='sold'"),
            "open_reports": n("SELECT COUNT(*) n FROM reports WHERE status='open'"),
            "revenue": n("SELECT COALESCE(SUM(amount),0) n FROM payment_orders WHERE status='paid'"),
            "paid_payments": n("SELECT COUNT(*) n FROM payment_orders WHERE status='paid'"),
            "pending_payments": n("SELECT COUNT(*) n FROM payment_orders WHERE status='pending'"),
            "active_boosts": n("SELECT COUNT(*) n FROM products WHERE featured=1 AND featured_until IS NOT NULL AND featured_until>?", (now_iso(),)),
            "views": n("SELECT COALESCE(SUM(views),0) n FROM products"),
        }
    return stats


@app.get("/api/admin/products")
def admin_products(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute(
            """SELECT p.*, u.name seller_name, u.email seller_email
               FROM products p LEFT JOIN users u ON u.id=p.seller_id
               ORDER BY p.created_at DESC LIMIT 500"""
        ).fetchall()
        return products_to_dicts(db, rows, user["id"])


@app.put("/api/admin/products/{product_id}/status")
def admin_product_status(product_id: str, payload: ModerationIn, user=Depends(admin_user)):
    if payload.status not in {"active", "paused", "rejected", "sold"}:
        raise HTTPException(400, "Status inválido")
    with conn() as db:
        db.execute("UPDATE products SET status=?,updated_at=? WHERE id=?", (payload.status, now_iso(), product_id))
        if db.total_changes == 0:
            raise HTTPException(404, "Anúncio não encontrado")
        db.commit()
    return {"ok": True}


@app.delete("/api/admin/products/{product_id}")
def admin_delete_product(product_id: str, user=Depends(admin_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        images = normalize_product_images(dict(row))
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
        db.commit()
    delete_product_images(images)
    return {"ok": True}


@app.get("/api/admin/users")
def admin_users(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute(
            """SELECT u.id,u.name,u.email,u.phone,u.role,u.verified,u.status,u.created_at,u.avatar_url,u.profile_review_status,u.profile_updated_at,
                      u.email_verified,u.email_verification_source,u.name_verification_status,u.phone_verification_status,u.address_verification_status,u.avatar_verification_status,
                      u.address_line,u.neighborhood,u.city,u.state,u.postal_code,
                      (SELECT COUNT(*) FROM products p WHERE p.seller_id=u.id) ad_count,
                      (SELECT COALESCE(SUM(po.amount),0) FROM payment_orders po WHERE po.user_id=u.id AND po.status='paid') paid_total
               FROM users u ORDER BY u.created_at DESC LIMIT 500"""
        ).fetchall()
    return [{**dict(r), "verified": bool(r["verified"])} for r in rows]


@app.put("/api/admin/users/{user_id}/verification/{field_name}")
def admin_verify_user_field(user_id: str, field_name: str, payload: VerifyIn, user=Depends(admin_user)):
    allowed = {"email", "name", "phone", "address", "avatar"}
    if field_name not in allowed:
        raise HTTPException(400, "Campo de verificação inválido")
    with conn() as db:
        target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Usuário não encontrado")
        if _is_master_account(target):
            row = _recompute_user_verification(db, user_id)
            db.commit()
            return {"ok": True, "message": "A conta Master possui verificação automática.", "user": user_public(row)}
        if payload.verified:
            if field_name == "name" and not str(_row_value(target, "name", "")).strip():
                raise HTTPException(400, "O usuário ainda não informou o nome")
            if field_name == "phone" and not str(_row_value(target, "phone", "")).strip():
                raise HTTPException(400, "O usuário ainda não informou o telefone")
            if field_name == "avatar" and not str(_row_value(target, "avatar_url", "")).strip():
                raise HTTPException(400, "O usuário ainda não enviou uma foto")
            if field_name == "address" and not _address_is_complete(
                str(_row_value(target, "address_line", "")), str(_row_value(target, "city", "")),
                str(_row_value(target, "state", "")), str(_row_value(target, "postal_code", ""))
            ):
                raise HTTPException(400, "O endereço ainda está incompleto")
        if field_name == "email":
            db.execute(
                "UPDATE users SET email_verified=?,email_verification_source=? WHERE id=?",
                (1 if payload.verified else 0, "master" if payload.verified else "", user_id),
            )
        else:
            column = VERIFICATION_FIELDS[field_name]
            status = "verified" if payload.verified else "unverified"
            db.execute(f"UPDATE users SET {column}=? WHERE id=?", (status, user_id))
        row = _recompute_user_verification(db, user_id)
        db.commit()
    return {"ok": True, "user": user_public(row)}


@app.put("/api/admin/users/{user_id}/verify")
def admin_verify_user(user_id: str, payload: VerifyIn, user=Depends(admin_user)):
    # Compatibilidade com versões anteriores do painel: nunca cria selo geral isoladamente.
    with conn() as db:
        target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Usuário não encontrado")
        if _is_master_account(target):
            _recompute_user_verification(db, user_id)
            db.commit()
            return {"ok": True, "message": "A conta Master possui verificação automática."}
        if payload.verified:
            if not str(_row_value(target, "name", "")).strip() or not str(_row_value(target, "phone", "")).strip() or not str(_row_value(target, "avatar_url", "")).strip():
                raise HTTPException(400, "Complete nome, telefone e foto antes da verificação geral")
            if not _address_is_complete(str(_row_value(target, "address_line", "")), str(_row_value(target, "city", "")), str(_row_value(target, "state", "")), str(_row_value(target, "postal_code", ""))):
                raise HTTPException(400, "Complete o endereço antes da verificação geral")
            db.execute("""UPDATE users SET email_verified=1,email_verification_source='master',
                name_verification_status='verified',phone_verification_status='verified',
                address_verification_status='verified',avatar_verification_status='verified' WHERE id=?""", (user_id,))
        else:
            db.execute("""UPDATE users SET email_verified=0,email_verification_source='',
                name_verification_status='unverified',phone_verification_status='unverified',
                address_verification_status='unverified',avatar_verification_status='unverified' WHERE id=?""", (user_id,))
        _recompute_user_verification(db, user_id)
        db.commit()
    return {"ok": True}


@app.put("/api/admin/users/{user_id}/status")
def admin_user_status(user_id: str, payload: AdminUserStatusIn, user=Depends(admin_user)):
    if payload.status not in {"active", "blocked"}:
        raise HTTPException(400, "Status inválido")
    if user_id == user["id"] and payload.status != "active":
        raise HTTPException(400, "Você não pode bloquear sua própria conta Master")
    with conn() as db:
        target = db.execute("SELECT id,email FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Usuário não encontrado")
        if str(target["email"] or "").strip().lower() == MASTER_EMAIL and payload.status != "active":
            raise HTTPException(400, "A conta Master não pode ser bloqueada")
        db.execute("UPDATE users SET status=? WHERE id=?", (payload.status, user_id))
        if db.total_changes == 0:
            raise HTTPException(404, "Usuário não encontrado")
        if payload.status != "active":
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        db.commit()
    return {"ok": True}


@app.put("/api/admin/users/{user_id}/role")
def admin_user_role(user_id: str, payload: AdminUserRoleIn, user=Depends(admin_user)):
    raise HTTPException(403, "O ClassificaJá permite somente um Master. Não é permitido criar outro administrador.")


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: str, user=Depends(admin_user)):
    if user_id == user["id"]:
        raise HTTPException(400, "Você não pode excluir sua própria conta administrativa")
    with conn() as db:
        target = db.execute("SELECT id,role,email FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Usuário não encontrado")
        if str(target["email"] or "").strip().lower() == MASTER_EMAIL:
            raise HTTPException(400, "A conta Master não pode ser excluída")
        rows = db.execute("SELECT * FROM products WHERE seller_id=?", (user_id,)).fetchall()
        images = []
        for row in rows:
            images.extend(normalize_product_images(dict(row)))
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()
    delete_product_images(images)
    return {"ok": True}


@app.get("/api/admin/plans")
def admin_plans(user=Depends(admin_user)):
    with conn() as db:
        return get_plan_catalog(db, include_inactive=True)


@app.put("/api/admin/plans/{plan_code}")
def admin_update_plan(plan_code: str, payload: AdminPlanIn, user=Depends(admin_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM plan_settings WHERE code=?", (plan_code,)).fetchone()
        if not row:
            raise HTTPException(404, "Plano não encontrado")
        current = plan_row_to_dict(row)
        updates = {}
        for key in ("name", "amount", "days", "ad_limit", "active", "badge", "tagline", "features", "limitations"):
            value = getattr(payload, key)
            if value is not None:
                updates[key] = value
        if not updates:
            return current
        if "amount" in updates and float(updates["amount"]) < 0:
            raise HTTPException(400, "Valor inválido")
        if "days" in updates and int(updates["days"]) < 0:
            raise HTTPException(400, "Duração inválida")
        if "ad_limit" in updates and int(updates["ad_limit"]) < 1:
            raise HTTPException(400, "O limite de anúncios precisa ser pelo menos 1")
        if current.get("free"):
            # O plano gratuito sempre mantém preço zero, mas a duração é definida pelo Master.
            updates["amount"] = 0.0
        fields = []
        values = []
        mapping = {
            "name": "name", "amount": "amount", "days": "days", "ad_limit": "ad_limit", "active": "active",
            "badge": "badge", "tagline": "tagline", "features": "features_json", "limitations": "limitations_json",
        }
        for key, value in updates.items():
            column = mapping[key]
            if key in {"features", "limitations"}:
                value = json.dumps(value, ensure_ascii=False)
            elif key == "active":
                value = 1 if value else 0
            fields.append(f"{column}=?")
            values.append(value)
        fields.append("updated_at=?")
        values.append(now_iso())
        db.execute(f"UPDATE plan_settings SET {', '.join(fields)} WHERE code=?", (*values, plan_code))
        db.commit()
        row = db.execute("SELECT * FROM plan_settings WHERE code=?", (plan_code,)).fetchone()
        return plan_row_to_dict(row)


@app.get("/api/admin/payments")
def admin_payments(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute(
            """SELECT po.*, u.name user_name, u.email user_email, p.title product_title
               FROM payment_orders po
               LEFT JOIN users u ON u.id=po.user_id
               LEFT JOIN products p ON p.id=po.product_id
               ORDER BY po.created_at DESC LIMIT 500"""
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            plan = get_plan(data.get("plan_code"), db, include_inactive=True) or {}
            if data.get("plan_code") == "boost_7" and float(data.get("amount") or 0) > 0:
                data["plan_name"] = "Básico legado 7 dias"
            else:
                data["plan_name"] = plan.get("name", data.get("plan_code"))
            result.append(data)
        return result


@app.post("/api/admin/payments/{payment_id}/cancel")
def admin_cancel_payment(payment_id: str, user=Depends(admin_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM payment_orders WHERE id=?", (payment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Pagamento não encontrado")
        if row["status"] != "pending":
            raise HTTPException(400, "Somente pagamentos pendentes podem ser cancelados")
        db.execute("UPDATE payment_orders SET status='cancelled' WHERE id=?", (payment_id,))
        db.commit()
    return {"ok": True}


def payment_integration_view(row):
    data = dict(row)
    provider = data.get("provider")
    definition = PAYMENT_PROVIDER_DEFS.get(provider, {})
    credentials = decrypt_payment_credentials(data.get("credentials_enc"))
    fields = []
    for field in definition.get("fields", []):
        key = field["key"]
        value = credentials.get(key)
        fields.append({
            **field,
            "configured": bool(value),
            "value": "" if field.get("secret") else (value or ""),
        })
    required = definition.get("required", [])
    configured = all(bool(credentials.get(key)) for key in required) if required else False
    return {
        "provider": provider,
        "label": definition.get("label", provider),
        "description": definition.get("description", ""),
        "enabled": bool(data.get("enabled")),
        "is_default": bool(data.get("is_default")),
        "mode": data.get("mode") or "sandbox",
        "configured": configured,
        "security_ready": bool(payment_fernet()),
        "fields": fields,
        "updated_at": data.get("updated_at"),
    }


PARTNER_SELF_SERVICE_RULES = {
    "plus": {
        "monthly_limit": 1,
        "label": "Plus",
        "slots": [
            {"code": "product_mid", "label": "Após a descrição nas páginas de anúncios"},
            {"code": "feed_end", "label": "Final do feed de anúncios"},
            {"code": "product_end", "label": "Rodapé das páginas de anúncios"},
        ],
    },
    "premium": {
        "monthly_limit": 2,
        "label": "Premium",
        "slots": [
            {"code": "home_top", "label": "Após Categorias na página inicial"},
            {"code": "product_top", "label": "Área nobre da página do anúncio"},
            {"code": "product_mid", "label": "Após a descrição nas páginas de anúncios"},
            {"code": "feed_end", "label": "Final do feed com prioridade"},
            {"code": "product_end", "label": "Rodapé das páginas de anúncios"},
        ],
    },
}


def partner_access_for_user(db, user_id: str):
    rows = db.execute(
        """SELECT id,title,boost_level,featured_until FROM products
           WHERE seller_id=? AND featured=1 AND featured_until IS NOT NULL AND featured_until>? AND boost_level>=2
           ORDER BY boost_level DESC, featured_until DESC""",
        (user_id, now_iso()),
    ).fetchall()
    if not rows:
        return {
            "eligible": False, "tier": None, "plan_name": "Grátis", "monthly_limit": 0,
            "used_this_month": 0, "remaining": 0, "slots": [], "active_until": None, "ads": []
        }
    top = dict(rows[0])
    tier = "premium" if int(top.get("boost_level") or 0) >= 3 else "plus"
    rule = PARTNER_SELF_SERVICE_RULES[tier]
    active_until = top.get("featured_until")
    month_prefix = now_dt().strftime("%Y-%m") + "%"
    used = db.execute(
        "SELECT COUNT(*) n FROM partner_ads WHERE owner_user_id=? AND source='user' AND created_at LIKE ?",
        (user_id, month_prefix),
    ).fetchone()["n"]
    ads = db.execute(
        "SELECT * FROM partner_ads WHERE owner_user_id=? AND source='user' ORDER BY created_at DESC LIMIT 12",
        (user_id,),
    ).fetchall()
    return {
        "eligible": True,
        "tier": tier,
        "plan_name": rule["label"],
        "monthly_limit": rule["monthly_limit"],
        "used_this_month": int(used or 0),
        "remaining": max(0, rule["monthly_limit"] - int(used or 0)),
        "slots": rule["slots"],
        "active_until": active_until,
        "ads": [dict(r) for r in ads],
    }


@app.get("/api/me/partner-benefit")
def my_partner_benefit(user=Depends(current_user)):
    with conn() as db:
        return partner_access_for_user(db, user["id"])


@app.post("/api/me/partner-ads/image")
async def my_partner_ad_image(image: UploadFile = File(...), user=Depends(current_user)):
    with conn() as db:
        access = partner_access_for_user(db, user["id"])
    if not access["eligible"]:
        raise HTTPException(403, "Parcerias estão disponíveis somente para planos Plus ou Premium ativos")
    if access["remaining"] <= 0:
        raise HTTPException(403, "Você já utilizou o limite de campanhas de parceria deste mês")
    image_url = await save_partner_image(image)
    return {"image_url": image_url}


@app.post("/api/me/partner-ads")
def my_create_partner_ad(payload: MyPartnerAdIn, user=Depends(current_user)):
    company = payload.company_name.strip()
    title = payload.title.strip()
    if not company or not title:
        raise HTTPException(400, "Empresa e título são obrigatórios")
    image_url = (payload.image_url or "").strip()
    target_url = (payload.target_url or "").strip()
    if not image_url:
        raise HTTPException(400, "Adicione uma imagem para a parceria")
    if image_url.startswith("/uploads/"):
        pass
    elif urlparse(image_url).scheme not in {"http", "https"}:
        raise HTTPException(400, "A URL da imagem precisa usar http ou https")
    if target_url and urlparse(target_url).scheme not in {"http", "https"}:
        raise HTTPException(400, "O link de destino precisa usar http ou https")
    with conn() as db:
        access = partner_access_for_user(db, user["id"])
        if not access["eligible"]:
            raise HTTPException(403, "Seu plano atual não inclui publicação de parceria")
        if access["remaining"] <= 0:
            raise HTTPException(403, "Limite mensal de campanhas atingido. Aguarde o próximo mês ou faça upgrade.")
        tier = access["tier"]
        plan_until = None
        try:
            plan_until = datetime.fromisoformat(access["active_until"]) if access.get("active_until") else None
        except Exception:
            plan_until = None
        max_until = now_dt() + timedelta(days=30)
        expires_dt = min(plan_until, max_until) if plan_until else max_until
        ad_id = str(uuid.uuid4())
        now = now_iso()
        db.execute(
            """INSERT INTO partner_ads(id,company_name,title,subtitle,image_url,target_url,placement,plan_tier,active,owner_user_id,source,expires_at,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ad_id, company, title, (payload.subtitle or "").strip(), image_url, target_url, "auto", tier, 1, user["id"], "user", expires_dt.isoformat(), now, now),
        )
        db.commit()
        row = db.execute("SELECT * FROM partner_ads WHERE id=?", (ad_id,)).fetchone()
    return dict(row)


@app.delete("/api/me/partner-ads/{ad_id}")
def my_deactivate_partner_ad(ad_id: str, user=Depends(current_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM partner_ads WHERE id=? AND owner_user_id=? AND source='user'", (ad_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Parceria não encontrada")
        db.execute("UPDATE partner_ads SET active=0,updated_at=? WHERE id=?", (now_iso(), ad_id))
        db.commit()
    return {"ok": True}


@app.get("/api/admin/home-slides")
def admin_home_slides(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute("SELECT * FROM home_slides ORDER BY sort_order ASC, created_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/home-slides/image")
async def admin_home_slide_image(image: UploadFile = File(...), user=Depends(admin_user)):
    image_url = await save_home_slide_image(image)
    return {"image_url": image_url}


@app.post("/api/admin/home-slides")
def admin_create_home_slide(payload: HomeSlideIn, user=Depends(admin_user)):
    image_url = (payload.image_url or "").strip()
    if not image_url:
        raise HTTPException(400, "Selecione uma imagem para o slider")
    slide_id = str(uuid.uuid4())
    now = now_iso()
    with conn() as db:
        db.execute(
            "INSERT INTO home_slides(id,title,subtitle,image_url,target_url,active,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (slide_id,(payload.title or "").strip(),(payload.subtitle or "").strip(),image_url,(payload.target_url or "").strip(),1 if payload.active else 0,int(payload.sort_order or 0),now,now),
        )
        db.commit()
        row = db.execute("SELECT * FROM home_slides WHERE id=?", (slide_id,)).fetchone()
    return dict(row)


@app.put("/api/admin/home-slides/{slide_id}")
def admin_update_home_slide(slide_id: str, payload: HomeSlideIn, user=Depends(admin_user)):
    image_url = (payload.image_url or "").strip()
    if not image_url:
        raise HTTPException(400, "Selecione uma imagem para o slider")
    with conn() as db:
        current = db.execute("SELECT * FROM home_slides WHERE id=?", (slide_id,)).fetchone()
        if not current:
            raise HTTPException(404, "Slide não encontrado")
        old_image = current["image_url"]
        db.execute(
            "UPDATE home_slides SET title=?,subtitle=?,image_url=?,target_url=?,active=?,sort_order=?,updated_at=? WHERE id=?",
            ((payload.title or "").strip(),(payload.subtitle or "").strip(),image_url,(payload.target_url or "").strip(),1 if payload.active else 0,int(payload.sort_order or 0),now_iso(),slide_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM home_slides WHERE id=?", (slide_id,)).fetchone()
    if old_image and old_image != image_url and (old_image.startswith("/uploads/") or (SUPABASE_URL and old_image.startswith(SUPABASE_URL))):
        delete_product_image(old_image)
    return dict(row)


@app.delete("/api/admin/home-slides/{slide_id}")
def admin_delete_home_slide(slide_id: str, user=Depends(admin_user)):
    with conn() as db:
        current = db.execute("SELECT * FROM home_slides WHERE id=?", (slide_id,)).fetchone()
        if not current:
            raise HTTPException(404, "Slide não encontrado")
        image_url = current["image_url"]
        db.execute("DELETE FROM home_slides WHERE id=?", (slide_id,))
        db.commit()
    if image_url and (image_url.startswith("/uploads/") or (SUPABASE_URL and image_url.startswith(SUPABASE_URL))):
        delete_product_image(image_url)
    return {"ok": True}


@app.get("/api/admin/partner-ads")
def admin_partner_ads(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute("SELECT * FROM partner_ads ORDER BY CASE plan_tier WHEN 'premium' THEN 3 WHEN 'plus' THEN 2 ELSE 1 END DESC, created_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/partner-ads/image")
async def admin_partner_ad_image(image: UploadFile = File(...), user=Depends(admin_user)):
    image_url = await save_partner_image(image)
    return {"image_url": image_url}


def normalize_partner_tier(value: str | None):
    tier = (value or "plus").strip().lower()
    aliases = {"plus": "plus", "premium": "premium"}
    tier = aliases.get(tier, tier)
    if tier not in {"plus", "premium"}:
        raise HTTPException(400, "Parcerias estão disponíveis somente nos planos Plus e Premium")
    return tier


@app.post("/api/admin/partner-ads")
def admin_create_partner_ad(payload: PartnerAdIn, user=Depends(admin_user)):
    tier = normalize_partner_tier(payload.plan_tier)
    if not payload.company_name.strip() or not payload.title.strip():
        raise HTTPException(400, "Empresa e título são obrigatórios")
    ad_id = str(uuid.uuid4())
    now = now_iso()
    with conn() as db:
        db.execute(
            "INSERT INTO partner_ads(id,company_name,title,subtitle,image_url,target_url,placement,plan_tier,active,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ad_id,payload.company_name.strip(),payload.title.strip(),(payload.subtitle or "").strip(),(payload.image_url or "").strip(),(payload.target_url or "").strip(),"auto",tier,1 if payload.active else 0,now,now),
        )
        db.commit()
        row = db.execute("SELECT * FROM partner_ads WHERE id=?", (ad_id,)).fetchone()
    return dict(row)


@app.put("/api/admin/partner-ads/{ad_id}")
def admin_update_partner_ad(ad_id: str, payload: PartnerAdIn, user=Depends(admin_user)):
    tier = normalize_partner_tier(payload.plan_tier)
    with conn() as db:
        current = db.execute("SELECT * FROM partner_ads WHERE id=?", (ad_id,)).fetchone()
        if not current:
            raise HTTPException(404, "Parceria não encontrada")
        old_image = current["image_url"]
        new_image = (payload.image_url or "").strip()
        db.execute(
            "UPDATE partner_ads SET company_name=?,title=?,subtitle=?,image_url=?,target_url=?,placement='auto',plan_tier=?,active=?,updated_at=? WHERE id=?",
            (payload.company_name.strip(),payload.title.strip(),(payload.subtitle or "").strip(),new_image,(payload.target_url or "").strip(),tier,1 if payload.active else 0,now_iso(),ad_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM partner_ads WHERE id=?", (ad_id,)).fetchone()
    if old_image and old_image != new_image and (old_image.startswith("/uploads/") or (SUPABASE_URL and old_image.startswith(SUPABASE_URL))):
        delete_product_image(old_image)
    return dict(row)


@app.delete("/api/admin/partner-ads/{ad_id}")
def admin_delete_partner_ad(ad_id: str, user=Depends(admin_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM partner_ads WHERE id=?", (ad_id,)).fetchone()
        if row:
            image_url = row["image_url"]
            db.execute("DELETE FROM partner_ads WHERE id=?", (ad_id,))
            db.commit()
        else:
            image_url = None
    if image_url and (image_url.startswith("/uploads/") or (SUPABASE_URL and image_url.startswith(SUPABASE_URL))):
        delete_product_image(image_url)
    return {"ok": True}


@app.get("/api/admin/payment-integrations")
def admin_payment_integrations(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute("SELECT * FROM payment_integrations ORDER BY provider").fetchall()
        by_provider = {r["provider"]: r for r in rows}
        result = []
        for provider in PAYMENT_PROVIDER_DEFS:
            row = by_provider.get(provider)
            if not row:
                db.execute(
                    "INSERT OR IGNORE INTO payment_integrations(provider,enabled,is_default,mode,credentials_enc,updated_at) VALUES (?,?,?,?,?,?)",
                    (provider, 0, 0, "sandbox", None, now_iso()),
                )
                row = db.execute("SELECT * FROM payment_integrations WHERE provider=?", (provider,)).fetchone()
            result.append(payment_integration_view(row))
        db.commit()
    return result


@app.put("/api/admin/payment-integrations/{provider}")
def admin_update_payment_integration(provider: str, payload: PaymentIntegrationIn, user=Depends(admin_user)):
    if provider not in PAYMENT_PROVIDER_DEFS:
        raise HTTPException(404, "Provedor de pagamento não suportado")
    if payload.mode not in {"sandbox", "production"}:
        raise HTTPException(400, "Ambiente inválido")
    with conn() as db:
        row = db.execute("SELECT * FROM payment_integrations WHERE provider=?", (provider,)).fetchone()
        if not row:
            db.execute(
                "INSERT OR IGNORE INTO payment_integrations(provider,enabled,is_default,mode,credentials_enc,updated_at) VALUES (?,?,?,?,?,?)",
                (provider, 0, 0, "sandbox", None, now_iso()),
            )
            row = db.execute("SELECT * FROM payment_integrations WHERE provider=?", (provider,)).fetchone()
        current = decrypt_payment_credentials(row["credentials_enc"])
        allowed_keys = {f["key"] for f in PAYMENT_PROVIDER_DEFS[provider].get("fields", [])}
        for key, value in (payload.credentials or {}).items():
            if key not in allowed_keys:
                continue
            cleaned = str(value or "").strip()
            if cleaned:
                current[key] = cleaned
        required = PAYMENT_PROVIDER_DEFS[provider].get("required", [])
        if payload.enabled and not all(bool(current.get(key)) for key in required):
            missing = [key for key in required if not current.get(key)]
            raise HTTPException(400, f"Preencha as credenciais obrigatórias: {', '.join(missing)}")
        encrypted = encrypt_payment_credentials(current) if current else None
        if payload.is_default:
            db.execute("UPDATE payment_integrations SET is_default=0")
        db.execute(
            "UPDATE payment_integrations SET enabled=?,is_default=?,mode=?,credentials_enc=?,updated_at=? WHERE provider=?",
            (1 if payload.enabled else 0, 1 if payload.is_default else 0, payload.mode, encrypted, now_iso(), provider),
        )
        db.commit()
        updated = db.execute("SELECT * FROM payment_integrations WHERE provider=?", (provider,)).fetchone()
    return payment_integration_view(updated)


@app.post("/api/admin/payment-integrations/pagbank/test")
def admin_test_pagbank_integration(user=Depends(admin_user)):
    import httpx
    with conn() as db:
        config = _pagbank_config(db, require_enabled=False)
    if not config:
        raise HTTPException(400, "Salve primeiro um Token PagBank no Painel Master")

    url = f"{_pagbank_base_url(config['mode'])}/public-keys/card"
    try:
        response = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {config['token']}",
                "Accept": "application/json",
            },
            timeout=20,
        )
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Não foi possível conectar ao PagBank: {exc.__class__.__name__}")

    try:
        payload = response.json()
    except Exception:
        payload = {}

    environment = "Produção" if config["mode"] == "production" else "Sandbox / Teste"
    if response.status_code == 200:
        return {
            "ok": True,
            "status_code": response.status_code,
            "environment": environment,
            "message": f"Token autenticado com sucesso no PagBank ({environment}).",
        }

    if response.status_code in {401, 403}:
        detail = payload.get("message") or payload.get("error") or payload.get("error_messages")
        raise HTTPException(
            response.status_code,
            f"PagBank recusou o token no ambiente {environment}. Confira se o token pertence a este mesmo ambiente. Detalhe: {detail or 'não autorizado'}",
        )

    # O endpoint de chave pública pode responder 400 quando a conta ainda não possui
    # chave pública de cartão. Nesse caso a chamada chegou autenticada ao PagBank, mas
    # não é seguro afirmar que a conta está pronta para PIX; mostramos o retorno exato.
    detail = payload.get("message") or payload.get("error") or payload.get("error_messages") or response.text[:300]
    return {
        "ok": False,
        "status_code": response.status_code,
        "environment": environment,
        "message": f"O PagBank respondeu HTTP {response.status_code}. A autenticação chegou à API, mas a conta precisa ser verificada antes do PIX. Detalhe: {detail}",
    }


@app.get("/api/admin/payment-integrations/default")
def admin_default_payment_integration(user=Depends(admin_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM payment_integrations WHERE is_default=1 AND enabled=1 LIMIT 1").fetchone()
    return payment_integration_view(row) if row else None


@app.get("/api/admin/reports")
def admin_reports(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute("""SELECT r.*, p.title product_title, u.name reporter_name
                           FROM reports r JOIN products p ON p.id=r.product_id JOIN users u ON u.id=r.reporter_id
                           ORDER BY r.created_at DESC LIMIT 500""").fetchall()
    return [dict(r) for r in rows]


@app.put("/api/admin/reports/{report_id}/resolve")
def resolve_report(report_id: str, user=Depends(admin_user)):
    with conn() as db:
        db.execute("UPDATE reports SET status='resolved',resolved_at=? WHERE id=?", (now_iso(), report_id))
        if db.total_changes == 0:
            raise HTTPException(404, "Denúncia não encontrada")
        db.commit()
    return {"ok": True}


# Production frontend ---------------------------------------------------------
# Docker/Railway builds frontend/dist. API routes and /docs are declared above this catch-all.
@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if not FRONTEND_DIST.exists():
        raise HTTPException(404, "Frontend ainda não foi compilado. Em desenvolvimento use npm run dev.")
    requested = (FRONTEND_DIST / full_path).resolve()
    try:
        requested.relative_to(FRONTEND_DIST.resolve())
    except ValueError:
        raise HTTPException(404, "Arquivo não encontrado")
    if full_path and requested.is_file():
        return FileResponse(requested)
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(404, "Frontend não encontrado")
