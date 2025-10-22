from telegram import ReplyKeyboardMarkup

def get_main_menu_keyboard():
    """Возвращает клавиатуру главного меню."""
    return ReplyKeyboardMarkup(
        [['Записаться на стирку'], ['Мои записи', 'История записей']],
        resize_keyboard=True
    )

def get_start_begin_keyboard(skip = False):
    if skip:
        return ReplyKeyboardMarkup([['Пропустить'], ['Начать заново']], one_time_keyboard=True,
                                       resize_keyboard=True)

    return ReplyKeyboardMarkup([['Начать заново']], one_time_keyboard=True, resize_keyboard=True)