#!/usr/bin/env python3
"""
==============================================================================
Конфигурационный модуль: CRM Group Manager (config.py)
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
Назначение: Парсинг переменных окружения, логер и валидация настроек сервиса.
==============================================================================
"""

import logging
import os
import sys
from pathlib import Path

# ==============================================================================
# 1. ПУТИ И ОКРУЖЕНИЕ
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def load_env(filepath: Path) -> None:
    """Безопасная загрузка .env без внешних зависимостей (Zero-Pip)."""
    if not filepath.exists():
        return
    with filepath.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val


load_env(ENV_PATH)

# ==============================================================================
# 2. ОСНОВНЫЕ ПАРАМЕТРЫ СЕРВИСА
# ==============================================================================

SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
SECRET_WEBHOOK_KEY: str = os.getenv("SECRET_WEBHOOK_KEY", "")

# Telegram MTProto
TG_API_ID: int = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH: str = os.getenv("TG_API_HASH", "")
TG_PHONE: str = os.getenv("TG_PHONE", "")
TG_CORPORATE_BOT_ID: str = os.getenv("TG_CORPORATE_BOT_ID", "@corp_bot")

# Мессенджер Макс (REST API)
MAX_API_URL: str = os.getenv("MAX_API_URL", "https://max.company.ru/api/v1")
MAX_API_TOKEN: str = os.getenv("MAX_API_TOKEN", "")
MAX_CORPORATE_BOT_ID: str = os.getenv("MAX_CORPORATE_BOT_ID", "max_corp_bot_id")

# Хранилище
DB_PATH: Path = BASE_DIR / os.getenv("DB_PATH", "crm_groups.db")

# Демо / Тестовый режим (True для работы без живых Telegram/Max учетных записей)
DEMO_MODE: bool = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

# ==============================================================================
# 3. НАСТРОЙКА ЛОГИРОВАНИЯ
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("CRM_Group_Manager")
