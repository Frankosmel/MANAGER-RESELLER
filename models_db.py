# app/models_db.py
import sqlite3, datetime as dt, re, uuid
from pathlib import Path
from .config import SET

DB = SET.data_dir / "state.sqlite3"

def cx():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with cx() as c:
        cur = c.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS resellers(
            id TEXT PRIMARY KEY,
            plan TEXT NOT NULL,          -- res_b|res_p|res_e
            started DATE NOT NULL,
            expires DATE NOT NULL,
            contact TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS clients(
            slug TEXT PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            username TEXT,
            reseller_id TEXT NOT NULL,
            plan TEXT NOT NULL,          -- plan_estandar/plus/pro (plantillas)
            expires DATE NOT NULL,
            created TEXT NOT NULL,
            workdir TEXT NOT NULL,
            svc_status TEXT NOT NULL DEFAULT 'stopped',
            FOREIGN KEY(reseller_id) REFERENCES resellers(id)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS payments(
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,          -- client|reseller
            type TEXT NOT NULL,          -- saldo|cup
            amount_usd REAL NOT NULL,
            amount_cup REAL NOT NULL,
            plan TEXT NOT NULL,          -- res_b|res_p|res_e|client_30|client_90|client_365
            item_id TEXT NOT NULL,       -- reseller_id o slug cliente
            receipt_msg_id INTEGER,
            status TEXT NOT NULL,        -- pending|approved|rejected
            created TEXT NOT NULL,
            rate_used REAL NOT NULL
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            meta TEXT,
            created TEXT NOT NULL
        )""")
        # defaults
        def put(k, v): cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, str(v)))
        put("owner_id", str(SET.owner_id or 0))
        put("usd_to_cup", "450")
        # precios reseller base (mensual)
        put("price_res_b", "10")
        put("price_res_p", "20")
        put("price_res_e", "30")
        # límites por plan (0 = ilimitado)
        put("limit_res_b", "3")
        put("limit_res_p", "10")
        put("limit_res_e", "0")
        # precios cliente (30/90/365 días)
        put("price_client_30", "5")
        put("price_client_90", "14")
        put("price_client_365", "50")
        # textos de pago
        put("pay_text_saldo", "💳 SALDO: Transfiere {monto_saldo} al 63785631 y pulsa ‘📤 Enviar comprobante’.")
        put("pay_text_cup", "🇨🇺 CUP: Envía {monto_cup} CUP a 9204 1299 7691 8161\n🔐 Confirmación: 56246700\nLuego pulsa ‘📤 Enviar comprobante’.")
        c.commit()

# ---- helpers ----
def get_setting(k, default=None):
    with cx() as c:
        cur=c.cursor(); cur.execute("SELECT value FROM settings WHERE key=?", (k,))
        r=cur.fetchone(); return r["value"] if r else default

def set_setting(k, v):
    with cx() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v))); c.commit()

def role_for(uid:int)->str:
    if str(uid) == get_setting("owner_id", "0"): return "boss"
    with cx() as c:
        cur=c.cursor()
        cur.execute("SELECT 1 FROM resellers WHERE id=?", (str(uid),))
        if cur.fetchone(): return "reseller"
        cur.execute("SELECT 1 FROM clients WHERE owner_id=?", (uid,))
        if cur.fetchone(): return "client"
    return "guest"

def limits(cur):
    cur.execute("SELECT key,value FROM settings WHERE key LIKE 'limit_%'")
    m = {r["key"]: int(r["value"]) for r in cur.fetchall()}
    return {"res_b": m.get("limit_res_b", 3),
            "res_p": m.get("limit_res_p", 10),
            "res_e": m.get("limit_res_e", 0)}

def prices(cur):
    cur.execute("SELECT key,value FROM settings WHERE key LIKE 'price_%' OR key='usd_to_cup'")
    m = {r["key"]: float(r["value"]) for r in cur.fetchall()}
    return {
        "usd_to_cup": m.get("usd_to_cup", 450.0),
        "res_b": m.get("price_res_b", 10.0),
        "res_p": m.get("price_res_p", 20.0),
        "res_e": m.get("price_res_e", 30.0),
        "c30":  m.get("price_client_30", 5.0),
        "c90":  m.get("price_client_90", 14.0),
        "c365": m.get("price_client_365", 50.0)
    }

def prorate(old_base:float, new_base:float, started:str, expires:str)->float:
    if new_base <= old_base: return 0.0
    s = dt.date.fromisoformat(started); e = dt.date.fromisoformat(expires); t = dt.date.today()
    if t >= e: return 0.0
    period = (e - s).days or 30
    left = (e - t).days
    return round((new_base - old_base) * left / period, 2)

def ensure_client_workdir(slug:str)->Path:
    p = SET.data_dir / "clients" / slug
    p.mkdir(parents=True, exist_ok=True)
    return p

def slugify(s:str)->str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "", s.strip().lstrip("@"))[:32]
    return s or "tenant"

def new_id()->str:
    return uuid.uuid4().hex[:12]

def iso_now()->str:
    return dt.datetime.now().isoformat(timespec="seconds")
