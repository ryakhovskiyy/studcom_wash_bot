import logging
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode
from telegram.error import BadRequest

from core.loader import sheet_manager
from keyboards.reply import get_main_menu_keyboard
from keyboards.inline import generate_filter_keyboard
from utils.states import *

# Импортируем наш новый сервис для управления напоминаниями
from services.reminders import schedule_booking_reminders

logger = logging.getLogger(__name__)


# --- ЛОГИКА БРОНИРОВАНИЯ ---

async def start_booking(update: Update, context: CallbackContext) -> int:
    """Начинает процесс бронирования слота."""
    user_id = update.effective_user.id

    user_data = sheet_manager.get_user(user_id)
    headers = sheet_manager.get_users_headers()
    user_dict = dict(zip(headers, user_data)) if user_data else {}

    if not user_data or user_dict.get('status') != 'ok':
        await update.message.reply_text(
            "Пожалуйста, заверши регистрацию, чтобы получить доступ к этой функции. Введи /start для перезапуска бота."
        )
        return MAIN_MENU

    if sheet_manager.get_user_bookings(user_id, upcoming_only=True):
        await update.message.reply_text("У тебя уже есть активная запись.", reply_markup=get_main_menu_keyboard())
        return MAIN_MENU

    context.user_data['booking_filters'] = {'dates': [], 'floors': [], 'times': []}
    await update.message.reply_text("Главное меню скрыто...", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("Выбери параметры для поиска слота:",
                                    reply_markup=generate_filter_keyboard(context))
    return BOOKING_FILTER_SETUP


async def booking_filters_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает нажатия на кнопки в меню фильтров."""
    query = update.callback_query
    await query.answer()

    context.user_data.setdefault('booking_filters', {'dates': [], 'floors': [], 'times': []})

    parts = query.data.split('_')
    action = parts[0]
    command = parts[1]

    if action == 'filter':
        if command == 'select':
            category = parts[2]
            return await show_filter_options(update, context, category=category)
        elif command == 'search':
            return await search_slots(update, context, page=0)
        elif command == 'tomenu':
            await query.message.delete()
            await query.message.reply_text("Ты в главном меню:", reply_markup=get_main_menu_keyboard())
            context.user_data.clear()
            return ConversationHandler.END
        elif command == 'back':
            return await back_to_filters_handler(update, context)

    elif action == 'option':
        command, value = parts[1], parts[2]
        category, item = value.split(':', 1)
        if command == 'toggle':
            target_list = context.user_data['booking_filters'].get(f"{category}s", [])
            if item in target_list:
                target_list.remove(item)
            else:
                target_list.append(item)
            page = context.user_data.get(f"{category}_page", 0)
            return await show_filter_options(update, context, category, page)
        elif command == 'set':
            context.user_data['booking_filters'][f"{category}s"] = [] if item == 'Любая' else [item]
            return await back_to_filters_handler(update, context)
        elif command == 'page':
            page = int(item)
            context.user_data[f"{category}_page"] = page
            return await show_filter_options(update, context, category, page)

    return BOOKING_FILTER_SETUP


async def show_filter_options(update: Update, context: CallbackContext, category: str, page: int = 0):
    """Показывает меню выбора для конкретного фильтра (даты, этажи, время)."""
    query = update.callback_query
    filters = context.user_data['booking_filters']
    keyboard = []
    text = ""

    if category == 'date':
        all_items = sheet_manager.get_unique_column_values('schedule', 'slot_date')
        selected = filters.get('dates', [])
        prefix_any = "✅ " if not selected else ""
        keyboard.append([InlineKeyboardButton(f"{prefix_any}🗓️ Любая дата", callback_data="option_set_date:Любая")])
        ITEMS_PER_PAGE = 5
        start_idx = page * ITEMS_PER_PAGE
        paginated_items = all_items[start_idx: start_idx + ITEMS_PER_PAGE]
        for item in paginated_items:
            prefix = "✅ " if item in selected else ""
            keyboard.append([InlineKeyboardButton(f"{prefix}{item[:-5]}", callback_data=f"option_toggle_date:{item}")])
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("◀️", callback_data=f"option_page_date:{page - 1}"))
        if len(all_items) > start_idx + ITEMS_PER_PAGE: nav.append(
            InlineKeyboardButton("▶️", callback_data=f"option_page_date:{page + 1}"))
        if nav: keyboard.append(nav)
        text = f"Выбери даты (Стр. {page + 1}):"

    elif category == 'floor':
        all_items = sheet_manager.get_unique_column_values('schedule', 'floor')
        selected = filters.get('floors', [])
        prefix_any = "✅ " if not selected else ""
        keyboard.append([InlineKeyboardButton(f"{prefix_any}🏢 Любой этаж", callback_data="option_set_floor:Любой")])
        for item in all_items:
            prefix = "✅ " if str(item) in selected else ""
            keyboard.append([InlineKeyboardButton(f"{prefix}{item}", callback_data=f"option_toggle_floor:{item}")])
        text = "Выбери этажи:"

    elif category == 'time':
        selected = filters.get('times', [])
        prefix_any = "✅ " if not selected else ""
        keyboard.append([InlineKeyboardButton(f"{prefix_any}🕒 Любое время", callback_data="option_set_time:Любая")])
        for item in ["Утро", "День", "Вечер"]:
            prefix = "✅ " if item in selected else ""
            keyboard.append([InlineKeyboardButton(f"{prefix}{item}", callback_data=f"option_toggle_time:{item}")])
        text = "Выбери промежутки времени:"

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="filter_back")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return BOOKING_FILTER_SETUP


async def back_to_filters_handler(update: Update, context: CallbackContext) -> int:
    """Возвращает пользователя в главное меню фильтров."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Выбери параметры для поиска слота:",
                                  reply_markup=generate_filter_keyboard(context))
    return BOOKING_FILTER_SETUP


async def search_slots(update: Update, context: CallbackContext, page: int = 0) -> int:
    """Ищет и отображает доступные слоты по заданным фильтрам."""
    query = update.callback_query or update
    if hasattr(query, 'answer'): await query.answer()
    context.user_data['current_page'] = page
    filters = context.user_data.get('booking_filters')
    available_slots = sheet_manager.get_available_slots(filters)
    if not available_slots:
        await query.message.edit_text("😔 Свободных слотов не найдено.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("⬅️ Изменить фильтры", callback_data="filter_back")]]))
        return BOOKING_FILTER_SETUP

    SLOTS_PER_PAGE = 5
    start_index = page * SLOTS_PER_PAGE
    end_index = start_index + SLOTS_PER_PAGE
    paginated_slots = available_slots[start_index:end_index]
    keyboard = []
    text = "Найденные свободные слоты:"
    for slot in paginated_slots:
        slot_text = f"{slot['slot_date'][:-5]} в {slot['start_time']} (Этаж {slot['floor']})"
        keyboard.append([InlineKeyboardButton(slot_text, callback_data=f"slot_{slot['row_index']}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("◀️ Пред. страница", callback_data=f"page_{page - 1}"))
    if len(available_slots) > end_index: nav.append(
        InlineKeyboardButton("След. страница ▶️", callback_data=f"page_{page + 1}"))
    if nav: keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("⬅️ Назад к фильтрам", callback_data="filter_back")])
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except BadRequest as e:
        if "Message is not modified" not in str(e): logger.warning(f"Error editing message: {e}")
    return VIEWING_SLOTS


async def handle_pagination(update: Update, context: CallbackContext) -> int:
    """Обрабатывает переключение страниц в списке слотов."""
    query = update.callback_query
    await query.answer()
    page = int(query.data.split('_')[1])
    return await search_slots(update, context, page=page)


async def select_slot(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор конкретного слота и запрашивает подтверждение."""
    query = update.callback_query
    await query.answer()
    row_index = int(query.data.split('_')[1])
    try:
        slot_data = dict(zip(sheet_manager.get_schedule_headers(), sheet_manager.schedule_sheet.row_values(row_index)))
        if not slot_data.get('slot_date'): raise ValueError("Слот пуст")
        confirm_text = (
            "Подтверди бронирование:\n\n"
            f"<b>Дата:</b> {slot_data['slot_date']}\n"
            f"<b>Время:</b> {slot_data['start_time']}\n"
            f"<b>Этаж:</b> {slot_data['floor']}"
        )
        keyboard = [[
            InlineKeyboardButton("✅ Да, забронировать", callback_data=f"confirm_book_{row_index}"),
            InlineKeyboardButton("⬅️ Нет, назад к слотам", callback_data="back_to_slots")
        ]]
        await query.edit_message_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode=ParseMode.HTML)
        return AWAITING_SLOT_CONFIRMATION
    except Exception as e:
        logger.warning(f"Ошибка при выборе слота (row {row_index}): {e}")
        await query.edit_message_text("Этот слот только что заняли. Пожалуйста, выбери другой.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_slots")]]))
        return VIEWING_SLOTS


async def confirm_booking(update: Update, context: CallbackContext) -> int:
    """Окончательно подтверждает бронь, сохраняет данные и планирует напоминания."""
    query = update.callback_query
    await query.answer("Бронирую...", show_alert=False)
    row_index = int(query.data.split('_')[-1])
    user = update.effective_user
    try:
        booking_result = sheet_manager.book_slot(
            slot_data={'row_index': row_index},
            user_info={'id': user.id, 'username': user.username or ""}
        )
        if booking_result:
            responsible = booking_result.get('responsible', 'Не назначен')
            contact = sheet_manager.get_config().get(f'responsible_{responsible}_contact', 'не указан')
            key_room = sheet_manager.get_config().get(f'responsible_{responsible}_key_room', 'не указана')
            success_text = (f"🎉 <b>Слот успешно забронирован!</b>\n\n"
                            f"Возьми ключ у ответственного в комнате <b>{key_room}</b>.\n\n"
                            f"<b>Твой ответственный:</b> {responsible}\n"
                            f"<b>Связь с ответственным:</b> {contact}\n")
            await query.edit_message_text(success_text, parse_mode=ParseMode.HTML)

            # Вызываем функцию для планирования всех напоминаний из нашего сервиса
            schedule_booking_reminders(context, user.id, booking_result)

        else:
            await query.edit_message_text("😔 <b>Упс!</b> Этот слот только что заняли.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Критическая ошибка при бронировании: {e}")
        await query.edit_message_text("Произошла серьезная ошибка при бронировании. Пожалуйста, сообщи об этом.")

    await query.message.reply_text("Ты в главном меню:", reply_markup=get_main_menu_keyboard())
    context.user_data.clear()
    context.user_data['in_main_menu'] = True
    return MAIN_MENU


async def back_to_slots_handler(update: Update, context: CallbackContext) -> int:
    """Возвращает пользователя к списку найденных слотов."""
    query = update.callback_query
    await query.answer()
    page = context.user_data.get('current_page', 0)
    return await search_slots(update, context, page=page)