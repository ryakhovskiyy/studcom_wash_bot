import logging
import sys

def setup_logging():
    """Настраивает два логгера:
    1. Системный логгер (INFO и выше) - выводится в консоль.
    2. Логгер действий пользователя (INFO) - выводится в файл user_activity.log.
    """

    # Настройка корневого логгера (для системы)
    # Удаляем все существующие обработчики, чтобы избежать дублирования
    logging.getLogger().handlers = []

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # Настройка логгера для действий пользователя
    user_logger = logging.getLogger("user_activity")
    user_logger.setLevel(logging.INFO)
    user_logger.propagate = False

    # Создаем файловый обработчик
    file_handler = logging.FileHandler("user_activity.log", mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    user_logger.addHandler(file_handler)