from telegram import ReplyKeyboardMarkup

def get_main_menu_keyboard():
    """Возвращает клавиатуру главного меню."""
    return ReplyKeyboardMarkup(
        [['Записаться на стирку'], ['Мои записи', 'История записей']],
        resize_keyboard=True
    )