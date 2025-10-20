import os
import logging
from telegram.ext import Application, PicklePersistence

from core.logging_config import setup_logging
from services.google_sheets import SheetManager
from dotenv import load_dotenv

# Загружаем переменные окружения в самом начале
load_dotenv()

# Настраиваем логирование
setup_logging()
logger = logging.getLogger(__name__)

# Инициализация менеджера таблиц
try:
    sheet_manager = SheetManager()
except Exception as e:
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось запустить SheetManager. {e}")
    exit()

# Инициализация persistence и самого приложения
persistence = PicklePersistence(filepath="bot_persistence")
token = os.getenv('TELEGRAM_TOKEN')
if not token:
    logger.critical("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_TOKEN не найден.")
    exit()

application = Application.builder().token(token).persistence(persistence).build()