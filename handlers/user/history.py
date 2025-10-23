import time
import logging

from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode
from telegram.error import BadRequest

from core.loader import sheet_manager
from keyboards.reply import get_main_menu_keyboard
from utils.states import *
from utils.decorators import block_check

# Импортируем функцию удаления напоминаний
from services.reminders import remove_reminders

logger = logging.getLogger(__name__)


@block_check
async def show_upcoming_bookings(update: Update, context: CallbackContext, from_menu: bool = False) -> int:
    query_or_message = update.callback_query or update.message
    is_command = (update.message is not None and
                  hasattr(update.message, 'text') and
                  update.message.text.startswith('/'))

    if from_menu or is_command:
        # Убираем клавиатуру главного меню
        temp_msg = await query_or_message.reply_text("Загружаю...", reply_markup=ReplyKeyboardRemove())
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=temp_msg.message_id)
        except BadRequest:
            pass

    user_id = update.effective_user.id
    time.sleep(0.1)  # Небольшая задержка для надежности
    bookings = sheet_manager.get_user_bookings(user_id, upcoming_only=True)

    if not bookings:
        await update.effective_message.reply_text("У тебя нет предстоящих записей.",
                                                  reply_markup=get_main_menu_keyboard())
        if update.callback_query:
            try:
                await update.callback_query.message.delete()
            except BadRequest:
                pass
        context.user_data['in_main_menu'] = True
        return MAIN_MENU

    keyboard = []
    text = "<b>Твои предстоящие записи:</b>\n\n"
    for i, booking in enumerate(bookings):
        booking_text = f"({i + 1}) {booking['slot_date']} в {booking['start_time']} (Этаж {booking['floor']})"
        text += f"• {booking_text}\n"
        keyboard.append([InlineKeyboardButton(f"❌ Отменить запись на {booking['slot_date']} ({i + 1})",
                                              callback_data=f"cancel_{booking['archive_row_index']}")])
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_main_menu_from_bookings")])

    if update.callback_query:
        await query_or_message.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                                 parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                                  parse_mode=ParseMode.HTML)
    return VIEWING_HISTORY


async def prompt_cancel_confirmation(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    archive_row_index = int(query.data.split('_')[1])
    keyboard = [[
        InlineKeyboardButton("✅ Да, отменить", callback_data=f"confirm_cancel_{archive_row_index}"),
        InlineKeyboardButton("⬅️ Нет, не отменять", callback_data="back_to_upcoming")
    ]]

    slot_row_list = sheet_manager.archive_sheet.row_values(archive_row_index)
    headers = sheet_manager.get_schedule_headers()
    slot_dict = dict(zip(headers, slot_row_list))
    await query.edit_message_text(f"Ты уверен, что хочешь отменить запись на <b>{slot_dict['slot_date']} с</b> "
                                  f"<b>{slot_dict['start_time']} по {slot_dict['end_time']} на {slot_dict['floor']}</b>?",
                                  reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return AWAITING_CANCEL_CONFIRMATION


async def confirm_cancellation(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer("Отменяю...")
    archive_row_index = int(query.data.split('_')[-1])
    user = update.effective_user
    username = user.username

    try:
        archive_headers = sheet_manager._archive_headers
        canceled_booking_data = dict(zip(archive_headers, sheet_manager.archive_sheet.row_values(archive_row_index)))

        if sheet_manager.cancel_booking(archive_row_index):
            await query.edit_message_text("✅ Запись успешно отменена.")
            remove_reminders(context, archive_row_index)

            responsible_name = canceled_booking_data.get('responsible')
            full_name = canceled_booking_data.get('full_name', f'ID: {user.id}')
            slot_text = f"{canceled_booking_data.get('slot_date')} с {canceled_booking_data.get('start_time')} до {canceled_booking_data.get('end_time')} (Этаж {canceled_booking_data.get('floor')})"

            # Ищем ID старосты
            monitor_id = None
            if responsible_name:
                config = sheet_manager.get_config()
                config_key_peer_id = f'responsible_{responsible_name}_peer_id'
                monitor_id_str = config.get(config_key_peer_id)
                if monitor_id_str:
                    try:
                        monitor_id = int(monitor_id_str)
                    except ValueError:
                        logger.error(
                            f"Не удалось прочитать peer_id для {responsible_name} при отмене. ID: {monitor_id_str}")
                else:
                    logger.warning(f"Не найден peer_id для {responsible_name} при отмене (ключ {config_key_peer_id})")

            if monitor_id:
                user_mention = f"(@{username})" if username else f"(ID: {user.id})"
                message_text = (
                    f"🚫 <b>Запись отменена!</b> 🚫\n\n"
                    f"Студент <b>{full_name}</b> {user_mention} отменил свою запись:\n\n"
                    f"<b>{slot_text}</b>"
                )
                try:
                    await context.bot.send_message(chat_id=monitor_id, text=message_text, parse_mode=ParseMode.HTML)
                    logger.info(f"Отправлено уведомление об отмене старосте {responsible_name} (ID: {monitor_id})")
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление об отмене старосте {monitor_id}: {e}")

        else:
            await query.edit_message_text("❌ Не удалось отменить запись (возможно, она уже была отменена).")

    except Exception as e:
        # Ловим ошибки, если не удалось получить данные из архива или при отмене
        logger.error(f"Ошибка при обработке отмены брони {archive_row_index}: {e}")
        await query.edit_message_text("❌ Произошла ошибка при отмене записи.")

    # Возвращаем в главное меню
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Ты в главном меню:",
        reply_markup=get_main_menu_keyboard()
    )
    context.user_data.clear()
    context.user_data['in_main_menu'] = True
    return MAIN_MENU


@block_check
async def show_booking_history(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    bookings = sheet_manager.get_user_bookings(user_id, upcoming_only=False)
    if not bookings:
        await update.message.reply_text("У тебя еще не было ни одной записи.", reply_markup=get_main_menu_keyboard())
        return MAIN_MENU

    text = "<b>Вся твоя история записей:</b>\n\n"
    for booking in bookings:
        status_icon = "✅" if booking.get('status') == 'Booked' else \
            ("❌" if booking.get('status') == 'Canceled' else "🕒")
        text += (f"{status_icon} {booking['slot_date']} c {booking['start_time']} до {booking['end_time']} "
                 f"(Этаж {booking['floor']}) - Статус: {booking.get('status', 'N/A')}\n")

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu_keyboard())
    context.user_data['in_main_menu'] = True
    return MAIN_MENU


async def back_to_main_menu_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    await query.message.reply_text("Ты в главном меню:", reply_markup=get_main_menu_keyboard())
    context.user_data.clear()
    context.user_data['in_main_menu'] = True
    return MAIN_MENU