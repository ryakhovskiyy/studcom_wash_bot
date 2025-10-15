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