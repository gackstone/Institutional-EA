"""
Telegram Configuration and Environment Loader.
Loads .env variables, validates credentials, and auto-discovers chat ID via getUpdates if needed.
"""

from __future__ import annotations
import os
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("TelegramConfig")


def load_env_file(env_path: Optional[str] = None) -> Dict[str, str]:
    """
    Loads environment variables from .env file into os.environ.
    Uses python-dotenv if installed, otherwise pure-Python parser.
    """
    if env_path is None:
        # Search in app data directory, current directory, parent directory, and project root
        from src.core.app_paths import get_base_app_data_dir
        app_data_env = get_base_app_data_dir() / ".env"
        env_override = os.environ.get("MT5_APP_DATA_DIR")
        candidates = [
            app_data_env,
            Path(env_override) / ".env" if env_override else None,
            Path(".env"),
            Path(__file__).resolve().parent.parent.parent / ".env",
            Path(os.getcwd()) / ".env"
        ]
        for c in candidates:
            if c and Path(c).exists():
                env_path = str(c)
                break

    loaded_vars: Dict[str, str] = {}
    if not env_path or not Path(env_path).exists():
        return loaded_vars

    try:
        import dotenv
        dotenv.load_dotenv(env_path, override=True)
    except ImportError:
        pass

    # Ensure all lines parsed even if python-dotenv missing
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                os.environ[k] = v
                loaded_vars[k] = v

    return loaded_vars


def save_env_value(key: str, value: str, env_path: Optional[str] = None) -> bool:
    """Updates or appends a key-value pair in .env file."""
    if env_path is None:
        env_path = str(Path(__file__).resolve().parent.parent.parent / ".env")

    path = Path(env_path)
    lines = []
    found = False

    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}={value}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ[key] = value
    return True


class TelegramConfig:
    def __init__(self, env_path: Optional[str] = None):
        self.env_path = env_path
        load_env_file(env_path)

        self.bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")
        self.proxy: Optional[str] = os.getenv("TELEGRAM_PROXY")

        # Sanitize chat_id (if user pasted t.me link or blank)
        if self.chat_id and ("t.me" in self.chat_id or not re.match(r"^-?\d+$", self.chat_id.strip())):
            logger.info("Provided TELEGRAM_CHAT_ID is not a numeric ID. Attempting auto-discovery via getUpdates...")
            self.chat_id = self.discover_chat_id()

        # Validation check
        self.validate()

    def discover_chat_id(self) -> Optional[str]:
        """Queries getUpdates to retrieve the chat_id of the most recent message."""
        if not self.bot_token:
            logger.warning("[Telegram] Cannot discover chat ID: TELEGRAM_BOT_TOKEN is missing.")
            return None

        from src.notifications.telegram_transport import TelegramTransport
        transport = TelegramTransport(self.bot_token, proxy=self.proxy)
        status, data, err = transport.request("GET", "getUpdates", timeout=10.0)

        if status == 200 and data.get("ok"):
            results = data.get("result", [])
            for item in reversed(results):
                msg = item.get("message") or item.get("channel_post") or item.get("edited_message")
                if msg and "chat" in msg and "id" in msg["chat"]:
                    found_id = str(msg["chat"]["id"])
                    logger.info(f"[Telegram] Discovered Chat ID: {found_id} (From: {msg.get('from', {}).get('first_name', 'Unknown')})")
                    save_env_value("TELEGRAM_CHAT_ID", found_id, self.env_path)
                    self.chat_id = found_id
                    return found_id

        logger.warning(f"[Telegram] Failed to discover chat ID via getUpdates. Status: {status}, Error: {err}")
        return None

    def get_status(self) -> str:
        """Returns Telegram state: CONFIGURED, DISABLED, or INVALID."""
        if not self.enabled:
            return "DISABLED"
        if not self.bot_token or not self.chat_id:
            return "DISABLED"
        if len(self.bot_token) < 20 or ":" not in self.bot_token:
            return "INVALID"
        return "CONFIGURED"

    def validate(self) -> bool:
        """Validates configuration smoothly while keeping trading engine operational."""
        missing = []
        if not self.bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            missing.append("TELEGRAM_CHAT_ID")

        if missing:
            if self.enabled:
                logger.info(f"[Telegram] Optional alerts disabled (unconfigured: {', '.join(missing)}). Trading logic continues unhindered.")
            self.enabled = False
            return False

        return self.enabled
