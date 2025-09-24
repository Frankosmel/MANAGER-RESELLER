import sqlite3
import datetime as dt
import re
import uuid
from pathlib import Path
from typing import Dict, Optional, Union
from .config import SET
import logging

# Configurar logging para depuración y auditoría
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=str(SET.data_dir / "logs" / "models_db.log")
)

# Ruta de la base de datos
DB = SET.data_dir / "state.sqlite3"

def cx() -> sqlite3.Connection:
    """
    Crea una conexión a la base de datos SQLite con el modo de fábrica de filas activado.

    Returns:
        sqlite3.Connection: Conexión a la base de datos.
    
    Raises:
        sqlite3.Error: Si no se puede conectar a la base de datos.
    """
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        logging.info(f"Conexión a la base de datos establecida: {DB}")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Error al conectar a la base de datos {DB}: {e}")
        raise RuntimeError(f"No se pudo conectar a la base de datos: {e}")

def init_db() -> None:
    """
    Inicializa la base de datos creando las tablas necesarias y estableciendo valores predeterminados.

    Tablas creadas:
        - settings: Almacena configuraciones clave-valor.
        - resellers: Datos de los resellers (ID, plan, fechas, contacto).
        - clients: Datos de los clientes (slug, propietario, reseller, plan, etc.).
        - payments: Registro de pagos (ID, usuario, monto, estado, etc.).
        - audit: Registro de auditoría para acciones del sistema.

    Valores predeterminados:
        - owner_id, usd_to_cup, precios de planes, límites de resellers, textos de pago.
    
    Raises:
        sqlite3.Error: Si ocurre un error al crear las tablas o insertar datos.
    """
    try:
        with cx() as c:
            cur = c.cursor()
            
            # Tabla settings
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Tabla resellers
            cur.execute("""
                CREATE TABLE IF NOT EXISTS resellers(
                    id TEXT PRIMARY KEY,
                    plan TEXT NOT NULL CHECK(plan IN ('res_b', 'res_p', 'res_e')),
                    started DATE NOT NULL,
                    expires DATE NOT NULL,
                    contact TEXT
                )
            """)
            
            # Tabla clients
            cur.execute("""
                CREATE TABLE IF NOT EXISTS clients(
                    slug TEXT PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    username TEXT,
                    reseller_id TEXT NOT NULL,
                    plan TEXT NOT NULL CHECK(plan IN ('plan_estandar', 'plan_plus', 'plan_pro')),
                    expires DATE NOT NULL,
                    created TEXT NOT NULL,
                    workdir TEXT NOT NULL,
                    svc_status TEXT NOT NULL DEFAULT 'stopped' CHECK(svc_status IN ('active', 'stopped', 'unknown')),
                    FOREIGN KEY(reseller_id) REFERENCES resellers(id)
                )
            """)
            
            # Tabla payments
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments(
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('client', 'reseller')),
                    type TEXT NOT NULL CHECK(type IN ('saldo', 'cup')),
                    amount_usd REAL NOT NULL CHECK(amount_usd >= 0),
                    amount_cup REAL NOT NULL CHECK(amount_cup >= 0),
                    plan TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    receipt_msg_id INTEGER,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
                    created TEXT NOT NULL,
                    rate_used REAL NOT NULL CHECK(rate_used >= 0)
                )
            """)
            
            # Tabla audit
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    meta TEXT,
                    created TEXT NOT NULL
                )
            """)
            
            # Valores predeterminados
            def put(k: str, v: Union[str, int, float]) -> None:
                try:
                    cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, str(v)))
                except sqlite3.Error as e:
                    logging.error(f"Error al insertar configuración {k}: {e}")
                    raise

            put("owner_id", str(SET.owner_id or 0))
            put("usd_to_cup", "450")
            # Precios reseller (mensual, en USD)
            put("price_res_b", "10")
            put("price_res_p", "20")
            put("price_res_e", "30")
            # Límites por plan (0 = ilimitado)
            put("limit_res_b", "3")
            put("limit_res_p", "10")
            put("limit_res_e", "0")
            # Precios cliente (30/90/365 días, en USD)
            put("price_client_30", "5")
            put("price_client_90", "14")
            put("price_client_365", "50")
            # Textos de pago
            put("pay_text_saldo", (
                "💳 **Pagar con saldo**\n"
                "Transfiere {monto_saldo} CUP al número 63785631.\n"
                "Luego, adjunta el comprobante en el chat."
            ))
            put("pay_text_cup", (
                "🇨🇺 **Pagar en CUP**\n"
                "Envía {monto_cup} CUP a la cuenta 9204 1299 7691 8161.\n"
                "🔐 Código de confirmación: 56246700\n"
                "Luego, adjunta el comprobante en el chat."
            ))
            put("support_contact", SET.support_contact)

            c.commit()
            logging.info("Base de datos inicializada correctamente con tablas y valores predeterminados.")
    except sqlite3.Error as e:
        logging.error(f"Error al inicializar la base de datos: {e}")
        raise RuntimeError(f"No se pudo inicializar la base de datos: {e}")

# ---- Helpers ----
def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Obtiene un valor de configuración de la tabla settings.

    Args:
        key (str): Clave de la configuración.
        default (Optional[str]): Valor predeterminado si la clave no existe.

    Returns:
        Optional[str]: Valor de la configuración o el valor predeterminado.
    
    Raises:
        sqlite3.Error: Si ocurre un error al consultar la base de datos.
    """
    try:
        with cx() as c:
            cur = c.cursor()
            cur.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cur.fetchone()
            value = row["value"] if row else default
            logging.debug(f"Obtenida configuración {key}: {value}")
            return value
    except sqlite3.Error as e:
        logging.error(f"Error al obtener configuración {key}: {e}")
        raise RuntimeError(f"No se pudo obtener la configuración {key}: {e}")

def set_setting(key: str, value: Union[str, int, float]) -> None:
    """
    Establece o actualiza un valor de configuración en la tabla settings.

    Args:
        key (str): Clave de la configuración.
        value (Union[str, int, float]): Valor a almacenar.

    Raises:
        sqlite3.Error: Si ocurre un error al actualizar la base de datos.
    """
    try:
        with cx() as c:
            cur = c.cursor()
            cur.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, str(value)))
            c.commit()
            logging.info(f"Configuración actualizada: {key} = {value}")
    except sqlite3.Error as e:
        logging.error(f"Error al establecer configuración {key}: {e}")
        raise RuntimeError(f"No se pudo actualizar la configuración {key}: {e}")

def role_for(uid: int) -> str:
    """
    Determina el rol de un usuario según su ID.

    Args:
        uid (int): ID del usuario en Telegram.

    Returns:
        str: Rol del usuario ("boss", "reseller", "client" o "guest").
    
    Raises:
        sqlite3.Error: Si ocurre un error al consultar la base de datos.
    """
    try:
        if str(uid) == get_setting("owner_id", "0"):
            logging.debug(f"Usuario {uid} identificado como boss.")
            return "boss"
        with cx() as c:
            cur = c.cursor()
            cur.execute("SELECT 1 FROM resellers WHERE id=?", (str(uid),))
            if cur.fetchone():
                logging.debug(f"Usuario {uid} identificado como reseller.")
                return "reseller"
            cur.execute("SELECT 1 FROM clients WHERE owner_id=?", (uid,))
            if cur.fetchone():
                logging.debug(f"Usuario {uid} identificado como client.")
                return "client"
        logging.debug(f"Usuario {uid} identificado como guest.")
        return "guest"
    except sqlite3.Error as e:
        logging.error(f"Error al determinar rol para usuario {uid}: {e}")
        raise RuntimeError(f"No se pudo determinar el rol del usuario {uid}: {e}")

def limits(cur: sqlite3.Cursor) -> Dict[str, int]:
    """
    Obtiene los límites de clientes por plan de reseller.

    Args:
        cur (sqlite3.Cursor): Cursor de la base de datos.

    Returns:
        Dict[str, int]: Diccionario con los límites por plan (res_b, res_p, res_e).
    
    Raises:
        sqlite3.Error: Si ocurre un error al consultar la base de datos.
    """
    try:
        cur.execute("SELECT key, value FROM settings WHERE key LIKE 'limit_%'")
        settings = {r["key"]: int(r["value"]) for r in cur.fetchall()}
        limits_dict = {
            "res_b": settings.get("limit_res_b", 3),
            "res_p": settings.get("limit_res_p", 10),
            "res_e": settings.get("limit_res_e", 0)
        }
        logging.debug(f"Límites obtenidos: {limits_dict}")
        return limits_dict
    except sqlite3.Error as e:
        logging.error(f"Error al obtener límites: {e}")
        raise RuntimeError(f"No se pudieron obtener los límites: {e}")

def prices(cur: sqlite3.Cursor) -> Dict[str, float]:
    """
    Obtiene los precios de los planes y la tasa de cambio USD a CUP.

    Args:
        cur (sqlite3.Cursor): Cursor de la base de datos.

    Returns:
        Dict[str, float]: Diccionario con precios y tasa de cambio.
    
    Raises:
        sqlite3.Error: Si ocurre un error al consultar la base de datos.
        ValueError: Si los valores no son numéricos válidos.
    """
    try:
        cur.execute("SELECT key, value FROM settings WHERE key LIKE 'price_%' OR key='usd_to_cup'")
        settings = {r["key"]: r["value"] for r in cur.fetchall()}
        prices_dict = {
            "usd_to_cup": float(settings.get("usd_to_cup", 450.0)),
            "res_b": float(settings.get("price_res_b", 10.0)),
            "res_p": float(settings.get("price_res_p", 20.0)),
            "res_e": float(settings.get("price_res_e", 30.0)),
            "c30": float(settings.get("price_client_30", 5.0)),
            "c90": float(settings.get("price_client_90", 14.0)),
            "c365": float(settings.get("price_client_365", 50.0))
        }
        for key, value in prices_dict.items():
            if value < 0:
                logging.error(f"Precio inválido para {key}: {value}")
                raise ValueError(f"El precio para {key} debe ser no negativo.")
        logging.debug(f"Precios obtenidos: {prices_dict}")
        return prices_dict
    except (sqlite3.Error, ValueError) as e:
        logging.error(f"Error al obtener precios: {e}")
        raise RuntimeError(f"No se pudieron obtener los precios: {e}")

def prorate(old_base: float, new_base: float, started: str, expires: str) -> float:
    """
    Calcula el costo prorrateado para actualizar un plan de reseller.

    Args:
        old_base (float): Precio del plan actual.
        new_base (float): Precio del nuevo plan.
        started (str): Fecha de inicio del plan actual (formato ISO).
        expires (str): Fecha de vencimiento del plan actual (formato ISO).

    Returns:
        float: Costo prorrateado (redondeado a 2 decimales).
    
    Raises:
        ValueError: Si las fechas o precios son inválidos.
    """
    try:
        if new_base <= old_base:
            logging.debug(f"No se aplica prorrateo: nuevo precio ({new_base}) <= precio actual ({old_base})")
            return 0.0
        start_date = dt.date.fromisoformat(started)
        expire_date = dt.date.fromisoformat(expires)
        today = dt.date.today()
        if today >= expire_date:
            logging.debug(f"No se aplica prorrateo: plan ya vencido ({expires})")
            return 0.0
        period = (expire_date - start_date).days or 30
        days_left = (expire_date - today).days
        prorate_cost = round((new_base - old_base) * days_left / period, 2)
        logging.debug(f"Prorrateo calculado: {prorate_cost} (días restantes: {days_left}/{period})")
        return prorate_cost
    except ValueError as e:
        logging.error(f"Error al calcular prorrateo: {e}")
        raise ValueError(f"Datos inválidos para prorrateo: {e}")

def ensure_client_workdir(slug: str) -> Path:
    """
    Crea el directorio de trabajo para un cliente si no existe.

    Args:
        slug (str): Slug del cliente.

    Returns:
        Path: Ruta del directorio de trabajo.
    
    Raises:
        ValueError: Si el slug está vacío.
        OSError: Si no se puede crear el directorio.
    """
    try:
        if not slug:
            logging.error("Slug vacío proporcionado para ensure_client_workdir.")
            raise ValueError("El slug del cliente no puede estar vacío.")
        workdir = SET.data_dir / "clients" / slug
        workdir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Directorio de cliente creado/existe: {workdir}")
        return workdir
    except (ValueError, OSError) as e:
        logging.error(f"Error al crear directorio para slug {slug}: {e}")
        raise RuntimeError(f"No se pudo crear el directorio para el cliente {slug}: {e}")

def slugify(s: str) -> str:
    """
    Genera un slug limpio a partir de una cadena.

    Args:
        s (str): Cadena a convertir en slug.

    Returns:
        str: Slug limpio (máximo 32 caracteres, solo alfanuméricos y guiones bajos).
    
    Raises:
        ValueError: Si el resultado es una cadena vacía.
    """
    try:
        slug = re.sub(r"[^a-zA-Z0-9_]+", "", s.strip().lstrip("@"))[:32]
        if not slug:
            logging.warning(f"Slug inválido generado a partir de: {s}. Usando 'tenant'.")
            slug = "tenant"
        logging.debug(f"Slug generado: {slug} (entrada: {s})")
        return slug
    except Exception as e:
        logging.error(f"Error al generar slug para {s}: {e}")
        raise RuntimeError(f"No se pudo generar slug: {e}")

def new_id() -> str:
    """
    Genera un ID único basado en UUID.

    Returns:
        str: ID único de 12 caracteres.
    """
    try:
        new_id = uuid.uuid4().hex[:12]
        logging.debug(f"ID generado: {new_id}")
        return new_id
    except Exception as e:
        logging.error(f"Error al generar ID: {e}")
        raise RuntimeError(f"No se pudo generar un ID único: {e}")

def iso_now() -> str:
    """
    Obtiene la fecha y hora actual en formato ISO con segundos.

    Returns:
        str: Fecha y hora en formato ISO (ej. "2025-09-24T10:44:00").
    """
    try:
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        logging.debug(f"Timestamp generado: {timestamp}")
        return timestamp
    except Exception as e:
        logging.error(f"Error al generar timestamp ISO: {e}")
        raise RuntimeError(f"No se pudo generar timestamp ISO: {e}")
