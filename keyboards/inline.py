from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def generate_filter_keyboard(context) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для меню фильтров бронирования."""
    filters = context.user_data.get('booking_filters', {})
    dates_text = ", ".join([d[:-5] for d in filters.get('dates', [])]) or "Любая"
    floors_text = ", ".join(filters.get('floors', [])) or "Любой"
    times_text = ", ".join(filters.get('times', [])) or "Любое"

    keyboard = [
        [InlineKeyboardButton(f"🗓️ Дата: {dates_text}", callback_data='filter_select_date')],
        [InlineKeyboardButton(f"🏢 Этаж: {floors_text}", callback_data='filter_select_floor')],
        [InlineKeyboardButton(f"🕒 Время: {times_text}", callback_data='filter_select_time')],
        [InlineKeyboardButton("🔍 Найти свободные слоты", callback_data='filter_search')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='filter_tomenu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_keyboard_summary() -> InlineKeyboardMarkup:
    keyboard = [[
        InlineKeyboardButton("✅ Подтвердить", callback_data='confirm_reg'),
        InlineKeyboardButton("🔄 Ввести заново", callback_data='retry_reg')
    ]]
    return InlineKeyboardMarkup(keyboard)

def get_keyboard_email() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔄 Отправить код еще раз", callback_data="resend_code")],
        [InlineKeyboardButton("✍️ Ввести другую почту", callback_data="change_email")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_keyboard_rules() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("✅ Я ознакомился и принимаю правила", callback_data='rules_accepted')]]
    return InlineKeyboardMarkup(keyboard)