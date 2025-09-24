import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import Optional
import logging

# Configurar logging para errores de configuración
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="config.log"
)

# Cargar variables de entorno desde el archivo .env
load_dotenv()

@dataclass
class Settings:
    """
    Clase para almacenar y validar la configuración del bot de Telegram.

    Atributos:
        api_id (int): ID de la API de Telegram, obtenido de my.telegram.org.
        api_hash (str): Hash de la API de Telegram, obtenido de my.telegram.org.
        bot_token (str): Token del bot, proporcionado por BotFather.
        owner_id (int): ID del usuario administrador principal (boss).
        data_dir (Path): Directorio base para datos, logs, facturas y clientes.
        tz (str): Zona horaria para operaciones del bot (por defecto, UTC).
        support_contact (str): Contacto de soporte (por ejemplo, @Soporte).
    """
    api_id: int = 0
    api_hash: str = ""
    bot_token: str = ""
    owner_id: int = 0
    data_dir: Path = Path("./data").absolute()
    tz: str = "UTC"
    support_contact: str = "@Soporte"

    def __post_init__(self):
        """
        Inicializa y valida las variables de entorno al crear una instancia de Settings.
        Convierte tipos y asigna valores predeterminados si es necesario.
        """
        # Obtener y validar API_ID
        try:
            self.api_id = int(os.getenv("API_ID", "0"))
            if self.api_id == 0:
                raise ValueError("API_ID no está configurado o es inválido.")
        except ValueError as e:
            logging.error(f"Error en API_ID: {e}")
            raise ValueError("API_ID debe ser un número entero válido en el archivo .env.")

        # Obtener y validar API_HASH
        self.api_hash = os.getenv("API_HASH", "")
        if not self.api_hash:
            logging.error("API_HASH no está configurado en el archivo .env.")
            raise ValueError("API_HASH debe estar configurado en el archivo .env.")

        # Obtener y validar BOT_TOKEN
        self.bot_token = os.getenv("BOT_TOKEN", "")
        if not self.bot_token:
            logging.error("BOT_TOKEN no está configurado en el archivo .env.")
            raise ValueError("BOT_TOKEN debe estar configurado en el archivo .env.")

        # Obtener y validar OWNER_ID
        try:
            self.owner_id = int(os.getenv("OWNER_ID", "0"))
        except ValueError:
            logging.warning("OWNER_ID no es válido, se usará 0 como predeterminado.")
            self.owner_id = 0

        # Configurar directorio de datos
        self.data_dir = Path(os.getenv("DATA_DIR", "./data")).absolute()
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.error(f"Error al crear el directorio de datos {self.data_dir}: {e}")
            raise RuntimeError(f"No se pudo crear el directorio de datos: {self.data_dir}")

        # Configurar zona horaria
        self.tz = os.getenv("TZ", "UTC")
        try:
            import pytz
            pytz.timezone(self.tz)  # Validar zona horaria
        except pytz.exceptions.UnknownTimeZoneError:
            logging.warning(f"Zona horaria inválida: {self.tz}. Se usará UTC.")
            self.tz = "UTC"

        # Configurar contacto de soporte
        self.support_contact = os.getenv("SUPPORT_CONTACT", "@Soporte")
        if not self.support_contact.startswith("@"):
            logging.warning(f"SUPPORT_CONTACT inválido: {self.support_contact}. Se usará @Soporte.")
            self.support_contact = "@Soporte"

    def ensure(self):
        """
        Crea los subdirectorios necesarios para el funcionamiento del bot.

        Subdirectorios:
            - logs: Para almacenar logs del sistema.
            - invoices: Para almacenar facturas o comprobantes.
            - clients: Para datos específicos de clientes.

        Returns:
            Settings: La instancia actual de la configuración.
        """
        try:
            for subdir in ("logs", "invoices", "clients"):
                subdir_path = self.data_dir / subdir
                subdir_path.mkdir(exist_ok=True)
                logging.info(f"Directorio creado/existe: {subdir_path}")
        except Exception as e:
            logging.error(f"Error al crear subdirectorios en {self.data_dir}: {e}")
            raise RuntimeError(f"No se pudieron crear los subdirectorios: {e}")
        return self

    def validate(self):
        """
        Valida que la configuración sea completa y válida antes de iniciar el bot.

        Raises:
            ValueError: Si falta alguna configuración crítica.
        """
        if not self.api_id:
            raise ValueError("API_ID es requerido para iniciar el bot.")
        if not self.api_hash:
            raise ValueError("API_HASH es requerido para iniciar el bot.")
        if not self.bot_token:
            raise ValueError("BOT_TOKEN es requerido para iniciar el bot.")
        logging.info("Configuración validada correctamente.")

# Crear instancia de configuración y asegurar directorios
try:
    SET = Settings().ensure()
    SET.validate()
    logging.info("Configuración cargada correctamente.")
except Exception as e:
    logging.error(f"Error al inicializar la configuración: {e}")
    raise
