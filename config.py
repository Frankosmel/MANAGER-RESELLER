# app/config.py
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    api_id: int = int(os.getenv("API_ID", "0"))
    api_hash: str = os.getenv("API_HASH", "")
    bot_token: str = os.getenv("BOT_TOKEN", "")
    owner_id: int = int(os.getenv("OWNER_ID", "0"))
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data")).absolute()
    tz: str = os.getenv("TZ", "UTC")

    def ensure(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for d in ("logs", "invoices", "clients"):
            (self.data_dir / d).mkdir(exist_ok=True)
        return self

SET = Settings().ensure()
