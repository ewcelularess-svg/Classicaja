from __future__ import annotations

import base64
import json
import hashlib
import os
import secrets
import sqlite3
import uuid
from urllib.parse import quote, unquote, urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet, InvalidToken

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "classificaja.db"
UPLOAD_DIR = BASE_DIR / "uploads"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgresql://", "postgres://"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SECRET_KEY") or "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "product-images").strip() or "product-images"
USE_SUPABASE_STORAGE = bool(SUPABASE_URL and SUPABASE_SECRET_KEY)
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "false" if USE_POSTGRES else "true").lower() in {"1", "true", "yes", "sim"}
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

PAYMENT_CONFIG_SECRET = (os.getenv("PAYMENT_CONFIG_KEY") or "").strip()
if not PAYMENT_CONFIG_SECRET:
    PAYMENT_CONFIG_SECRET = "|".join(x for x in [SUPABASE_SECRET_KEY, os.getenv("ADMIN_PASSWORD", "").strip()] if x)

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
    f = payment_fernet()
    if not f:
        return {}
    try:
        return json.loads(f.decrypt(token.encode("utf-8")).decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
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

app = FastAPI(title="ClassificaJá API", version="2.16.6")
_cors = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


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


async def save_product_image(image: UploadFile):
    ext = Path(image.filename or "image.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Formato de imagem não suportado")
    content = await image.read()
    if len(content) > 7 * 1024 * 1024:
        raise HTTPException(400, "Imagem maior que 7 MB")
    filename = f"products/{uuid.uuid4().hex}{ext}"
    if USE_SUPABASE_STORAGE:
        import httpx
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": image.content_type or "image/jpeg",
            "x-upsert": "false",
        }
        url = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET)}/{quote(filename, safe='/')}"
        response = httpx.post(url, headers=headers, content=content, timeout=30)
        if response.status_code >= 300:
            raise HTTPException(502, f"Falha ao enviar imagem ao Supabase Storage: {response.text[:180]}")
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
    local_name = Path(filename).name
    (UPLOAD_DIR / local_name).write_bytes(content)
    return f"/uploads/{local_name}"


async def save_partner_image(image: UploadFile):
    ext = Path(image.filename or "partner.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Formato de imagem não suportado. Use JPG, PNG ou WEBP")
    content = await image.read()
    if len(content) > 7 * 1024 * 1024:
        raise HTTPException(400, "Imagem maior que 7 MB")
    filename = f"partners/{uuid.uuid4().hex}{ext}"
    if USE_SUPABASE_STORAGE:
        import httpx
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": image.content_type or "image/jpeg",
            "x-upsert": "false",
        }
        url = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET)}/{quote(filename, safe='/')}"
        response = httpx.post(url, headers=headers, content=content, timeout=30)
        if response.status_code >= 300:
            raise HTTPException(502, f"Falha ao enviar imagem da parceria: {response.text[:180]}")
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
    local_name = f"partner_{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / local_name).write_bytes(content)
    return f"/uploads/{local_name}"


async def save_home_slide_image(image: UploadFile):
    ext = Path(image.filename or "home-slide.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Formato de imagem não suportado. Use JPG, PNG ou WEBP")
    content = await image.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Imagem maior que 10 MB")
    filename = f"home-slides/{uuid.uuid4().hex}{ext}"
    if USE_SUPABASE_STORAGE:
        import httpx
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": image.content_type or "image/jpeg",
            "x-upsert": "false",
        }
        url = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET)}/{quote(filename, safe='/')}"
        response = httpx.post(url, headers=headers, content=content, timeout=30)
        if response.status_code >= 300:
            raise HTTPException(502, f"Falha ao enviar imagem do slider: {response.text[:180]}")
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
    local_name = f"home_slide_{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / local_name).write_bytes(content)
    return f"/uploads/{local_name}"



async def save_profile_image(image: UploadFile):
    ext = Path(image.filename or "profile.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Formato de imagem não suportado. Use JPG, PNG ou WEBP")
    content = await image.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Foto maior que 5 MB")
    filename = f"profiles/{uuid.uuid4().hex}{ext}"
    if USE_SUPABASE_STORAGE:
        import httpx
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": image.content_type or "image/jpeg",
            "x-upsert": "false",
        }
        url = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET)}/{quote(filename, safe='/')}"
        response = httpx.post(url, headers=headers, content=content, timeout=30)
        if response.status_code >= 300:
            raise HTTPException(502, f"Falha ao enviar foto do perfil: {response.text[:180]}")
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
    local_name = f"profile_{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / local_name).write_bytes(content)
    return f"/uploads/{local_name}"

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
        ensure_column(db, "users", "auth_provider", "TEXT NOT NULL DEFAULT 'local'")
        ensure_column(db, "sessions", "auth_provider", "TEXT NOT NULL DEFAULT 'local'")
        ensure_column(db, "sessions", "authenticated_at", "TEXT")
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
        ensure_column(db, "products", "neighborhood", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "products", "status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(db, "products", "featured_until", "TEXT")
        ensure_column(db, "products", "boost_level", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "products", "updated_at", "TEXT")
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
                """INSERT OR IGNORE INTO plan_settings(code,name,amount,days,boost,free,active,badge,tagline,features_json,limitations_json,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    code, plan.get("name", code), float(plan.get("amount") or 0), int(plan.get("days") or 0),
                    int(plan.get("boost") or 0), 1 if plan.get("free") else 0, 1, plan.get("badge", ""),
                    plan.get("tagline", ""), json.dumps(plan.get("features", []), ensure_ascii=False),
                    json.dumps(plan.get("limitations", []), ensure_ascii=False), now_iso(),
                ),
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


class AdminUserStatusIn(BaseModel):
    status: str


class AdminUserRoleIn(BaseModel):
    role: str


class AdminPlanIn(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    days: Optional[int] = None
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


def set_publish_plan_access(db, user_id: str, plan_code: str, status: str = "ready", payment_order_id: str | None = None, product_id: str | None = None):
    now = now_iso()
    db.execute(
        """INSERT INTO publish_plan_access(user_id,plan_code,status,payment_order_id,product_id,selected_at,updated_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
             plan_code=excluded.plan_code,
             status=excluded.status,
             payment_order_id=excluded.payment_order_id,
             product_id=excluded.product_id,
             selected_at=excluded.selected_at,
             updated_at=excluded.updated_at""",
        (user_id, plan_code, status, payment_order_id, product_id, now, now),
    )


def get_publish_plan_access(db, user_id: str):
    row = db.execute("SELECT * FROM publish_plan_access WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        free_used = bool(db.execute("SELECT 1 FROM free_plan_usage WHERE user_id=?", (user_id,)).fetchone())
        return {"ready": False, "status": "none", "plan": None, "free_used": free_used, "free_available": not free_used}
    data = dict(row)
    plan = get_plan(data.get("plan_code"), db, include_inactive=True)
    free_used = bool(db.execute("SELECT 1 FROM free_plan_usage WHERE user_id=?", (user_id,)).fetchone())
    return {
        "ready": data.get("status") == "ready" and bool(plan),
        "status": data.get("status") or "none",
        "plan": plan,
        "payment_order_id": data.get("payment_order_id"),
        "product_id": data.get("product_id"),
        "selected_at": data.get("selected_at"),
        "free_used": free_used,
        "free_available": not free_used,
    }


def create_session(db, user_id: str, provider: str = "local"):
    token = secrets.token_urlsafe(32)
    expires = (now_dt() + timedelta(days=30)).isoformat()
    authenticated_at = now_iso()
    db.execute(
        "INSERT INTO sessions(token,user_id,expires_at,auth_provider,authenticated_at) VALUES (?,?,?,?,?)",
        (token, user_id, expires, provider or "local", authenticated_at),
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
        "auth_provider": value("auth_provider", "local"),
        "has_password": bool(value("password_salt") and value("password_hash")),
    }


def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Faça login para continuar")
    token = authorization.split(" ", 1)[1]
    with conn() as db:
        row = db.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token=? AND s.expires_at>?""",
            (token, now_iso()),
        ).fetchone()
    if not row or row["status"] != "active":
        raise HTTPException(401, "Sessão inválida, expirada ou conta bloqueada")
    return dict(row)


def current_auth_context(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Faça login para continuar")
    token = authorization.split(" ", 1)[1]
    with conn() as db:
        row = db.execute(
            """SELECT u.*, s.auth_provider AS session_auth_provider, s.authenticated_at AS session_authenticated_at
               FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token=? AND s.expires_at>?""",
            (token, now_iso()),
        ).fetchone()
    if not row or row["status"] != "active":
        raise HTTPException(401, "Sessão inválida ou expirada")
    return row


def _row_value(row, key, default=""):
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    return row[key] if key in keys and row[key] is not None else default


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
        row = db.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?",
            (token, now_iso()),
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


@app.get("/api/health")
def health():
    return {"ok": True, "service": "ClassificaJá", "version": "2.16.6", "database": "postgresql" if USE_POSTGRES else "sqlite", "storage": "supabase" if USE_SUPABASE_STORAGE else "local"}


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
                if identity.get("email_verified") and not bool(_row_value(user, "email_verified", 0)):
                    updates.append("email_verified=1")
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
                        avatar_url,email_verified,auth_provider,profile_review_status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        uid, identity.get("name") or email.split("@", 1)[0], email, "", "", "", now_iso(),
                        "user", 0, "active", identity.get("avatar_url") or None,
                        1 if identity.get("email_verified") else 0, provider, "unverified",
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
    if len(payload.password) < 6:
        raise HTTPException(400, "A senha precisa ter pelo menos 6 caracteres")
    if not payload.name.strip() or "@" not in payload.email:
        raise HTTPException(400, "Nome e e-mail válidos são obrigatórios")
    uid = str(uuid.uuid4())
    salt, pwhash = hash_password(payload.password)
    try:
        with conn() as db:
            db.execute(
                """INSERT INTO users(id,name,email,phone,password_salt,password_hash,created_at,role,verified,status,email_verified,auth_provider)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, payload.name.strip(), payload.email.lower().strip(), payload.phone.strip(), salt, pwhash, now_iso(), "user", 0, "active", 0, "local"),
            )
            token = create_session(db, uid, "local")
            row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    except DBIntegrityError:
        raise HTTPException(409, "Este e-mail já está cadastrado")
    return {"token": token, "user": user_public(row)}


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
    with conn() as db:
        db.execute(
            """UPDATE users SET name=?,phone=?,address_line=?,neighborhood=?,city=?,state=?,postal_code=?,
               verified=0,profile_review_status='pending',profile_updated_at=? WHERE id=?""",
            (name, phone_digits, payload.address_line.strip(), payload.neighborhood.strip(), payload.city.strip(), state, postal_digits, now_iso(), user["id"]),
        )
        db.commit()
        row = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    return {"ok": True, "message": "Dados salvos e enviados para verificação do Master", "user": user_public(row)}


@app.post("/api/me/avatar")
async def update_my_avatar(current_password: str = Form(""), image: UploadFile = File(...), user=Depends(current_auth_context)):
    _confirm_sensitive_action(user, current_password)
    new_url = await save_profile_image(image)
    old_url = _row_value(user, "avatar_url", "")
    with conn() as db:
        db.execute(
            "UPDATE users SET avatar_url=?,verified=0,profile_review_status='pending',profile_updated_at=? WHERE id=?",
            (new_url, now_iso(), user["id"]),
        )
        db.commit()
        row = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    if old_url and old_url != new_url:
        delete_product_image(old_url)
    return {"ok": True, "message": "Foto atualizada e enviada para verificação do Master", "user": user_public(row)}


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
        db.commit()
    return {"ok": True, "message": "Senha alterada com sucesso" if had_password else "Senha criada com sucesso. Agora você também pode entrar por e-mail e senha"}


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
        where.append("(title LIKE ? OR description LIKE ? OR city LIKE ? OR neighborhood LIKE ?)")
        q = f"%{search.strip()}%"
        args += [q, q, q, q]
    if category.strip():
        where.append("category_slug=?")
        args.append(category.strip())
    if city.strip():
        where.append("city LIKE ?")
        args.append(f"%{city.strip()}%")
    if neighborhood.strip():
        where.append("neighborhood LIKE ?")
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
        return [product_dict(db, r, user["id"] if user else None) for r in rows]


@app.get("/api/products/{product_id}")
def get_product(product_id: str, user=Depends(optional_user)):
    with conn() as db:
        cleanup_expired_features(db)
        db.commit()
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row or (row["status"] != "active" and (not user or (row["seller_id"] != user["id"] and user["role"] != "admin"))):
            raise HTTPException(404, "Anúncio não encontrado")
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
            return [product_dict(db, r, user["id"] if user else None) for r in items[:limit]]

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
            return [product_dict(db, r, user["id"] if user else None) for r in items[:limit]]

        # 3) Mesma cidade, qualquer categoria, priorizando preço próximo.
        rows = db.execute(
            """SELECT * FROM products
               WHERE status='active' AND id<>? AND city=?
               ORDER BY ABS(price-?), boost_level DESC, created_at DESC
               LIMIT ?""",
            (product_id, base["city"], price, limit * 3),
        ).fetchall()
        if add_rows(rows):
            return [product_dict(db, r, user["id"] if user else None) for r in items[:limit]]

        # 4) Último fallback: outros anúncios ativos do marketplace.
        rows = db.execute(
            """SELECT * FROM products
               WHERE status='active' AND id<>?
               ORDER BY ABS(price-?), boost_level DESC, views DESC, created_at DESC
               LIMIT ?""",
            (product_id, price, limit * 4),
        ).fetchall()
        add_rows(rows)

        return [product_dict(db, r, user["id"] if user else None) for r in items[:limit]]


@app.post("/api/products")
async def create_product(
    title: str = Form(...), description: str = Form(...), price: float = Form(...), category_slug: str = Form(...),
    city: str = Form(...), state: str = Form(...), neighborhood: str = Form(""), condition: str = Form("Usado"),
    original_price: float | None = Form(default=None), payment_mode: str = Form("cash"),
    images: list[UploadFile] = File(default=[]), image: UploadFile | None = File(default=None), user=Depends(current_user),
):
    if price < 0:
        raise HTTPException(400, "Preço inválido")
    payment_mode = str(payment_mode or "cash").strip().lower()
    if payment_mode not in {"cash", "installments"}:
        raise HTTPException(400, "Forma de venda inválida")
    gallery_files = [img for img in (images or []) if getattr(img, "filename", None)]
    if image and image.filename:
        gallery_files.insert(0, image)
    gallery_urls = []
    for img in gallery_files[:8]:
        gallery_urls.append(await save_product_image(img))
    image_url = gallery_urls[0] if gallery_urls else None
    if original_price is not None and original_price <= price:
        original_price = None
    pid = str(uuid.uuid4())
    with conn() as db:
        access_row = db.execute("SELECT * FROM publish_plan_access WHERE user_id=? AND status='ready'", (user["id"],)).fetchone()
        if not access_row:
            raise HTTPException(403, "Escolha um plano antes de publicar o anúncio")
        access_data = dict(access_row)
        selected_plan = get_plan(access_data.get("plan_code"), db, include_inactive=True)
        if not selected_plan:
            raise HTTPException(403, "O plano selecionado não está mais disponível")
        if not db.execute("SELECT 1 FROM categories WHERE slug=?", (category_slug,)).fetchone():
            raise HTTPException(400, "Categoria inválida")
        created_at = now_iso()
        boost_level = int(selected_plan.get("boost") or 0)
        is_featured = 1 if boost_level > 0 else 0
        plan_days = max(0, int(selected_plan.get("days") or 0))
        featured_until = None
        plan_expires_at = (now_dt() + timedelta(days=plan_days)).isoformat() if plan_days else None
        if is_featured:
            featured_until = plan_expires_at
        if selected_plan.get("code") == "boost_7":
            if db.execute("SELECT 1 FROM free_plan_usage WHERE user_id=?", (user["id"],)).fetchone():
                raise HTTPException(403, "O Plano Grátis já foi utilizado nesta conta. Escolha Plus ou Premium.")
        db.execute(
            """INSERT INTO products(id,seller_id,title,description,price,category_slug,city,state,neighborhood,condition,image_url,image_urls,original_price,payment_mode,status,featured,featured_until,boost_level,plan_code,plan_expires_at,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, user["id"], title.strip(), description.strip(), price, category_slug, city.strip(), state.strip().upper(), neighborhood.strip(), condition, image_url, json.dumps(gallery_urls), original_price, payment_mode, "active", is_featured, featured_until, boost_level, selected_plan.get("code"), plan_expires_at, created_at, created_at),
        )
        if selected_plan.get("code") == "boost_7":
            db.execute(
                """INSERT INTO free_plan_usage(user_id,product_id,used_at) VALUES (?,?,?)
                   ON CONFLICT(user_id) DO NOTHING""",
                (user["id"], pid, created_at),
            )
        db.execute(
            "UPDATE publish_plan_access SET status='used',product_id=?,updated_at=? WHERE user_id=?",
            (pid, created_at, user["id"]),
        )
        if access_data.get("payment_order_id"):
            db.execute("UPDATE payment_orders SET product_id=? WHERE id=?", (pid, access_data["payment_order_id"]))
        db.execute(
            "INSERT INTO notifications(id,type,product_id,title,body,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), "new_product", pid, "Novo anúncio publicado", f"{title.strip()} • {city.strip()} - {state.strip().upper()}", created_at),
        )
        db.commit()
    return {"id": pid, "plan_code": selected_plan.get("code")}


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
    with conn() as db:
        db.execute("UPDATE products SET image_url=?,image_urls=?,updated_at=? WHERE id=?", (image_url, json.dumps([image_url]), now_iso(), product_id))
        db.commit()
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
    for img in files[:8]:
        gallery_urls.append(await save_product_image(img))
    with conn() as db:
        db.execute("UPDATE products SET image_url=?,image_urls=?,updated_at=? WHERE id=?", (gallery_urls[0], json.dumps(gallery_urls), now_iso(), product_id))
        db.commit()
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
    for img in files[:available]:
        gallery_urls.append(await save_product_image(img))
    with conn() as db:
        primary = gallery_urls[0] if gallery_urls else None
        db.execute("UPDATE products SET image_url=?,image_urls=?,updated_at=? WHERE id=?", (primary, json.dumps(gallery_urls), now_iso(), product_id))
        db.commit()
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
        return [product_dict(db, r, user["id"]) for r in rows]


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
    current_meta = plan_meta_from_boost(highest_boost) or {"name": "Grátis", "code": "boost_7"}
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
        return [product_dict(db, r, user["id"]) for r in rows]


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
            db.commit()
        else:
            cid = c["id"]
    return {"conversation_id": cid}


def conversation_dict(db, row, me_id):
    data = dict(row)
    p = db.execute("SELECT id,title,price,image_url,status FROM products WHERE id=?", (row["product_id"],)).fetchone()
    other_id = row["seller_id"] if row["buyer_id"] == me_id else row["buyer_id"]
    other = db.execute("SELECT id,name,verified FROM users WHERE id=?", (other_id,)).fetchone()
    last = db.execute("SELECT body,created_at FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT 1", (row["id"],)).fetchone()
    unread = db.execute("SELECT COUNT(*) n FROM messages WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL", (row["id"], me_id)).fetchone()["n"]
    data["product"] = dict(p) if p else None
    data["other_user"] = dict(other) if other else None
    if data["other_user"]:
        data["other_user"]["verified"] = bool(data["other_user"]["verified"])
    data["last_message"] = dict(last) if last else None
    data["unread"] = unread
    return data


@app.get("/api/me/conversations")
def my_conversations(user=Depends(current_user)):
    with conn() as db:
        rows = db.execute("SELECT * FROM conversations WHERE buyer_id=? OR seller_id=? ORDER BY updated_at DESC", (user["id"], user["id"])).fetchall()
        return [conversation_dict(db, r, user["id"]) for r in rows]


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
        rid = str(uuid.uuid4())
        db.execute("INSERT INTO reports(id,reporter_id,product_id,reason,details,status,created_at) VALUES (?,?,?,?,?,'open',?)", (rid, user["id"], product_id, payload.reason.strip(), payload.details.strip(), now_iso()))
        db.commit()
    return {"id": rid, "ok": True}


# Plans / payments -----------------------------------------------------------

def _digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _validate_tax_id(value: str | None) -> str:
    tax_id = _digits(value)
    if len(tax_id) not in {11, 14}:
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
    if order_data.get("product_id") and plan:
        product = db.execute("SELECT featured_until FROM products WHERE id=?", (order_data["product_id"],)).fetchone()
        base_dt = now_dt()
        if product and product["featured_until"]:
            try:
                current_until = datetime.fromisoformat(product["featured_until"])
                if current_until > base_dt:
                    base_dt = current_until
            except Exception:
                pass
        until = (base_dt + timedelta(days=int(plan.get("days") or 0))).isoformat()
        db.execute(
            "UPDATE products SET featured=1,featured_until=?,boost_level=?,plan_code=?,plan_expires_at=?,status='active',updated_at=? WHERE id=?",
            (until, int(plan.get("boost") or 0), order_data.get("plan_code"), until, now_iso(), order_data["product_id"]),
        )
    elif plan:
        # Compra feita antes da publicação: libera uma nova publicação com este plano.
        set_publish_plan_access(db, order_data["user_id"], order_data["plan_code"], "ready", order_data["id"], None)


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
        if plan.get("free") or float(plan.get("amount") or 0) <= 0:
            # Plano Grátis: cortesia de uso único por conta; não cria cobrança.
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
        return [product_dict(db, r, user["id"]) for r in rows]


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
                      (SELECT COUNT(*) FROM products p WHERE p.seller_id=u.id) ad_count,
                      (SELECT COALESCE(SUM(po.amount),0) FROM payment_orders po WHERE po.user_id=u.id AND po.status='paid') paid_total
               FROM users u ORDER BY u.created_at DESC LIMIT 500"""
        ).fetchall()
    return [{**dict(r), "verified": bool(r["verified"])} for r in rows]


@app.put("/api/admin/users/{user_id}/verify")
def admin_verify_user(user_id: str, payload: VerifyIn, user=Depends(admin_user)):
    with conn() as db:
        db.execute("UPDATE users SET verified=?,profile_review_status=? WHERE id=?", (1 if payload.verified else 0, "verified" if payload.verified else "unverified", user_id))
        if db.total_changes == 0:
            raise HTTPException(404, "Usuário não encontrado")
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
        for key in ("name", "amount", "days", "active", "badge", "tagline", "features", "limitations"):
            value = getattr(payload, key)
            if value is not None:
                updates[key] = value
        if not updates:
            return current
        if "amount" in updates and float(updates["amount"]) < 0:
            raise HTTPException(400, "Valor inválido")
        if "days" in updates and int(updates["days"]) < 0:
            raise HTTPException(400, "Duração inválida")
        if current.get("free"):
            # O plano gratuito sempre mantém preço zero, mas a duração é definida pelo Master.
            updates["amount"] = 0.0
        fields = []
        values = []
        mapping = {
            "name": "name", "amount": "amount", "days": "days", "active": "active",
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
# Render builds frontend/dist. API routes and /docs are declared above this catch-all.
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
