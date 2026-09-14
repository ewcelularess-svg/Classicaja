from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sqlite3
import uuid
from urllib.parse import quote, unquote, urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

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

app = FastAPI(title="ClassificaJá API", version="2.2.1")
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
    salt = base64.b64decode(salt_b64)
    _, candidate = hash_password(password, salt)
    return secrets.compare_digest(candidate, digest_b64)


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
            """
        )
        # Migrations for V1 installations.
        ensure_column(db, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
        ensure_column(db, "users", "verified", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "users", "status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(db, "users", "avatar_url", "TEXT")
        ensure_column(db, "products", "neighborhood", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "products", "status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(db, "products", "featured_until", "TEXT")
        ensure_column(db, "products", "boost_level", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "products", "updated_at", "TEXT")

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

        # Production admin comes from environment variables; demo data stays local-only by default.
        admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        if admin_email and admin_password:
            existing_admin = db.execute("SELECT * FROM users WHERE email=?", (admin_email,)).fetchone()
            if not existing_admin:
                salt, pwhash = hash_password(admin_password)
                db.execute(
                    "INSERT INTO users(id,name,email,phone,password_salt,password_hash,created_at,role,verified,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), os.getenv("ADMIN_NAME", "Administrador"), admin_email, os.getenv("ADMIN_PHONE", ""), salt, pwhash, now_iso(), "admin", 1, "active"),
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


class MessageIn(BaseModel):
    body: str


class ReportIn(BaseModel):
    reason: str
    details: str = ""


class PaymentIn(BaseModel):
    product_id: Optional[str] = None
    plan_code: str
    method: str = "pix"


class ModerationIn(BaseModel):
    status: str


class VerifyIn(BaseModel):
    verified: bool


PLANS = {
    "boost_7": {
        "name": "Destaque Básico 7 dias",
        "amount": 19.90,
        "days": 7,
        "boost": 1,
        "badge": "Entrada",
        "tagline": "Plano econômico para começar a destacar seu anúncio.",
        "features": [
            "Selo de anúncio em destaque",
            "Prioridade básica nas buscas",
            "7 dias de visibilidade reforçada"
        ]
    },
    "boost_15": {
        "name": "Destaque Plus 15 dias",
        "amount": 34.90,
        "days": 15,
        "boost": 2,
        "badge": "Intermediário",
        "tagline": "Mais tempo no topo e mais força para vender rápido.",
        "features": [
            "Tudo do plano Básico",
            "Maior prioridade nas buscas",
            "Mais tempo em evidência",
            "Melhor posição no catálogo"
        ]
    },
    "boost_30": {
        "name": "Destaque Premium 30 dias",
        "amount": 59.90,
        "days": 30,
        "boost": 3,
        "badge": "Mais completo",
        "tagline": "O máximo de visibilidade para vender com mais velocidade.",
        "features": [
            "Tudo do plano Plus",
            "Prioridade máxima nas buscas",
            "30 dias de destaque premium",
            "Mais visualizações no catálogo",
            "Maior exposição entre os anúncios"
        ]
    },
}


def create_session(db, user_id: str):
    token = secrets.token_urlsafe(32)
    expires = (now_dt() + timedelta(days=30)).isoformat()
    db.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES (?,?,?)", (token, user_id, expires))
    db.commit()
    return token


def user_public(row):
    return {
        "id": row["id"], "name": row["name"], "email": row["email"], "phone": row["phone"],
        "role": row["role"], "verified": bool(row["verified"]), "status": row["status"],
        "created_at": row["created_at"],
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
    if user["role"] != "admin":
        raise HTTPException(403, "Acesso restrito ao administrador")
    return user


def cleanup_expired_features(db):
    db.execute("UPDATE products SET featured=0,boost_level=0 WHERE featured_until IS NOT NULL AND featured_until<=?", (now_iso(),))


def product_dict(db, row, user_id: str | None = None):
    data = dict(row)
    seller = db.execute("SELECT id,name,phone,verified,created_at FROM users WHERE id=?", (data["seller_id"],)).fetchone()
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
    return data


@app.get("/api/health")
def health():
    return {"ok": True, "service": "ClassificaJá", "version": "2.2.0", "database": "postgresql" if USE_POSTGRES else "sqlite", "storage": "supabase" if USE_SUPABASE_STORAGE else "local"}


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
                "INSERT INTO users(id,name,email,phone,password_salt,password_hash,created_at,role,verified,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (uid, payload.name.strip(), payload.email.lower().strip(), payload.phone.strip(), salt, pwhash, now_iso(), "user", 0, "active"),
            )
            token = create_session(db, uid)
            row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    except DBIntegrityError:
        raise HTTPException(409, "Este e-mail já está cadastrado")
    return {"token": token, "user": user_public(row)}


@app.post("/api/auth/login")
def login(payload: LoginIn):
    with conn() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (payload.email.lower().strip(),)).fetchone()
        if not user or not verify_password(payload.password, user["password_salt"], user["password_hash"]):
            raise HTTPException(401, "E-mail ou senha incorretos")
        if user["status"] != "active":
            raise HTTPException(403, "Conta indisponível")
        token = create_session(db, user["id"])
    return {"token": token, "user": user_public(user)}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user_public(user)


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


@app.get("/api/products")
def list_products(search: str = "", category: str = "", city: str = "", neighborhood: str = "", sort: str = "newest", limit: int = 50, user=Depends(optional_user)):
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
        rows = db.execute(f"SELECT * FROM products WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?", (*args, min(limit, 100))).fetchall()
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


@app.post("/api/products")
async def create_product(
    title: str = Form(...), description: str = Form(...), price: float = Form(...), category_slug: str = Form(...),
    city: str = Form(...), state: str = Form(...), neighborhood: str = Form(""), condition: str = Form("Usado"),
    image: UploadFile | None = File(default=None), user=Depends(current_user),
):
    if price < 0:
        raise HTTPException(400, "Preço inválido")
    image_url = None
    if image and image.filename:
        image_url = await save_product_image(image)
    pid = str(uuid.uuid4())
    with conn() as db:
        if not db.execute("SELECT 1 FROM categories WHERE slug=?", (category_slug,)).fetchone():
            raise HTTPException(400, "Categoria inválida")
        db.execute(
            """INSERT INTO products(id,seller_id,title,description,price,category_slug,city,state,neighborhood,condition,image_url,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, user["id"], title.strip(), description.strip(), price, category_slug, city.strip(), state.strip().upper(), neighborhood.strip(), condition, image_url, "active", now_iso(), now_iso()),
        )
        db.commit()
    return {"id": pid}


@app.put("/api/products/{product_id}")
def update_product(product_id: str, payload: dict, user=Depends(current_user)):
    allowed = {"title", "description", "price", "category_slug", "city", "state", "neighborhood", "condition", "status"}
    fields = [(k, payload[k]) for k in payload if k in allowed]
    if not fields:
        raise HTTPException(400, "Nenhum campo válido")
    if "status" in payload and payload["status"] not in {"active", "sold", "paused"}:
        raise HTTPException(400, "Status inválido")
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode editar este anúncio")
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
        old_image = row["image_url"]

    image_url = await save_product_image(image)
    with conn() as db:
        db.execute("UPDATE products SET image_url=?,updated_at=? WHERE id=?", (image_url, now_iso(), product_id))
        db.commit()
    if old_image and old_image != image_url:
        delete_product_image(old_image)
    return {"ok": True, "image_url": image_url}


@app.delete("/api/products/{product_id}")
def delete_product(product_id: str, user=Depends(current_user)):
    with conn() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Anúncio não encontrado")
        if row["seller_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Você não pode excluir este anúncio")
        delete_product_image(row["image_url"])
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
        db.commit()
    return {"ok": True}


@app.get("/api/me/products")
def my_products(user=Depends(current_user)):
    with conn() as db:
        rows = db.execute("SELECT * FROM products WHERE seller_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        return [product_dict(db, r, user["id"]) for r in rows]


@app.get("/api/me/dashboard")
def my_dashboard(user=Depends(current_user)):
    with conn() as db:
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
    return {"total": row["total"] or 0, "active": row["active"] or 0, "sold": row["sold"] or 0, "views": row["views"] or 0, "favorites_received": favs, "unread_messages": unread}


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
        db.execute("UPDATE messages SET read_at=? WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL", (now_iso(), conversation_id, user["id"]))
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
        mid = str(uuid.uuid4())
        db.execute("INSERT INTO messages(id,conversation_id,sender_id,body,created_at) VALUES (?,?,?,?,?)", (mid, conversation_id, user["id"], body, now_iso()))
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now_iso(), conversation_id))
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
@app.get("/api/plans")
def plans():
    return [{"code": code, **plan} for code, plan in PLANS.items()]


@app.post("/api/payments")
def create_payment(payload: PaymentIn, user=Depends(current_user)):
    if payload.plan_code not in PLANS:
        raise HTTPException(400, "Plano inválido")
    if payload.method not in {"pix", "card"}:
        raise HTTPException(400, "Forma de pagamento inválida")
    plan = PLANS[payload.plan_code]
    with conn() as db:
        if payload.product_id:
            p = db.execute("SELECT * FROM products WHERE id=?", (payload.product_id,)).fetchone()
            if not p or p["seller_id"] != user["id"]:
                raise HTTPException(403, "Anúncio inválido")
        oid = str(uuid.uuid4())
        db.execute("INSERT INTO payment_orders(id,user_id,product_id,plan_code,amount,method,status,created_at) VALUES (?,?,?,?,?,?,?,?)", (oid, user["id"], payload.product_id, payload.plan_code, plan["amount"], payload.method, "pending", now_iso()))
        db.commit()
    return {"id": oid, "status": "pending", "amount": plan["amount"], "method": payload.method, "checkout_mode": "demo", "pix_code": f"DEMO-PIX-{oid[:8].upper()}" if payload.method == "pix" else None}


@app.post("/api/payments/{payment_id}/demo-confirm")
def demo_confirm_payment(payment_id: str, user=Depends(current_user)):
    """Development helper. Replace by gateway webhook in production."""
    with conn() as db:
        order = db.execute("SELECT * FROM payment_orders WHERE id=?", (payment_id,)).fetchone()
        if not order or order["user_id"] != user["id"]:
            raise HTTPException(404, "Pagamento não encontrado")
        if order["status"] == "paid":
            return {"ok": True, "status": "paid"}
        plan = PLANS.get(order["plan_code"])
        paid_at = now_iso()
        db.execute("UPDATE payment_orders SET status='paid',paid_at=? WHERE id=?", (paid_at, payment_id))
        if order["product_id"] and plan:
            until = (now_dt() + timedelta(days=plan["days"])).isoformat()
            db.execute("UPDATE products SET featured=1,featured_until=?,boost_level=?,updated_at=? WHERE id=?", (until, plan["boost"], now_iso(), order["product_id"]))
        db.commit()
    return {"ok": True, "status": "paid"}


@app.get("/api/me/payments")
def my_payments(user=Depends(current_user)):
    with conn() as db:
        rows = db.execute("SELECT * FROM payment_orders WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
    return [dict(r) for r in rows]


# Admin ----------------------------------------------------------------------
@app.get("/api/admin/stats")
def admin_stats(user=Depends(admin_user)):
    with conn() as db:
        users = db.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        products = db.execute("SELECT COUNT(*) n FROM products").fetchone()["n"]
        active = db.execute("SELECT COUNT(*) n FROM products WHERE status='active'").fetchone()["n"]
        reports = db.execute("SELECT COUNT(*) n FROM reports WHERE status='open'").fetchone()["n"]
        revenue = db.execute("SELECT COALESCE(SUM(amount),0) n FROM payment_orders WHERE status='paid'").fetchone()["n"]
        views = db.execute("SELECT COALESCE(SUM(views),0) n FROM products").fetchone()["n"]
    return {"users": users, "products": products, "active_products": active, "open_reports": reports, "revenue": revenue, "views": views}


@app.get("/api/admin/products")
def admin_products(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute("SELECT * FROM products ORDER BY created_at DESC LIMIT 200").fetchall()
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


@app.get("/api/admin/users")
def admin_users(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute("SELECT id,name,email,phone,role,verified,status,created_at FROM users ORDER BY created_at DESC LIMIT 200").fetchall()
    return [{**dict(r), "verified": bool(r["verified"])} for r in rows]


@app.put("/api/admin/users/{user_id}/verify")
def admin_verify_user(user_id: str, payload: VerifyIn, user=Depends(admin_user)):
    with conn() as db:
        db.execute("UPDATE users SET verified=? WHERE id=?", (1 if payload.verified else 0, user_id))
        if db.total_changes == 0:
            raise HTTPException(404, "Usuário não encontrado")
        db.commit()
    return {"ok": True}


@app.get("/api/admin/reports")
def admin_reports(user=Depends(admin_user)):
    with conn() as db:
        rows = db.execute("""SELECT r.*, p.title product_title, u.name reporter_name
                           FROM reports r JOIN products p ON p.id=r.product_id JOIN users u ON u.id=r.reporter_id
                           ORDER BY r.created_at DESC LIMIT 200""").fetchall()
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
