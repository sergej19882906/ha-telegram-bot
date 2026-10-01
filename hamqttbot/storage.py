"""Работа с файлами данных (data/): языки, чаты для уведомлений, миграция."""

import json
import os
from pathlib import Path

from .config import logger

# Путь к файлам данных
# В Docker: /app/data/
# Локально: папка data/ рядом с корнем проекта
SCRIPT_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR") or SCRIPT_DIR / "data")
LANG_FILE = DATA_DIR / "user_langs.json"
TIMERS_FILE = DATA_DIR / "timers.json"
CHATS_FILE = DATA_DIR / "known_chats.json"


def load_user_langs() -> dict:
    """Загружает выбранные языки пользователей из файла."""
    if LANG_FILE.exists():
        try:
            return json.loads(LANG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Не удалось прочитать %s: %s", LANG_FILE, e)
    return {}


def save_user_langs(langs: dict):
    """Сохраняет выбранные языки пользователей в файл."""
    try:
        LANG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LANG_FILE.write_text(
            json.dumps(langs, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning("Не удалось записать %s: %s", LANG_FILE, e)


def load_known_chats() -> set:
    """Загружает известные чаты (адресаты уведомлений) из файла."""
    if CHATS_FILE.exists():
        try:
            data = json.loads(CHATS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {int(c) for c in data}
        except Exception as e:
            logger.warning("Не удалось прочитать %s: %s", CHATS_FILE, e)
    return set()


def save_known_chats(chats: set):
    """Сохраняет известные чаты в файл."""
    try:
        CHATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CHATS_FILE.write_text(json.dumps(sorted(chats)), encoding="utf-8")
    except Exception as e:
        logger.warning("Не удалось записать %s: %s", CHATS_FILE, e)


USER_LANGS = load_user_langs()


def migrate_legacy_data_files():
    """Переносит data-файлы из корня проекта (формат до 2.1.6) в DATA_DIR."""
    if DATA_DIR.resolve() == SCRIPT_DIR.resolve():
        return  # DATA_DIR — корень проекта: переносить нечего
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("user_langs.json", "timers.json"):
        legacy = SCRIPT_DIR / name
        if not legacy.exists():
            continue
        target = DATA_DIR / name
        if target.exists():
            logger.warning(
                "Не переношу %s: в %s уже есть %s — оставляю оба, "
                "актуальным считается %s", legacy, DATA_DIR, name, target
            )
            continue
        try:
            legacy.replace(target)
            logger.info("Перенесён %s → %s", legacy, target)
        except Exception as e:
            logger.warning("Не удалось перенести %s: %s", legacy, e)
