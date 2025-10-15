from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode

from bot_commands import COMMANDS_INFO, HELP_MESSAGE
from core.loader import sheet_manager
from utils.decorators import block_check
from utils.states import (
    MAIN_MENU, AWAITING_SURNAME, AWAITING_EMAIL
)
from keyboards.reply import get_main_menu_keyboard

# Импортируем хендлеры из других файлов, чтобы передавать управление
from .user import booking, history


@block_check
async def start(update: Update, context: CallbackContext) -> int:
    """Обрабатывает команду /start, проверяет регистрацию и направляет пользователя."""
    user = update.effective_user
    context.user_data.clear()
    user_data_from_sheet = sheet_manager.get_user(user.id)

    if user_data_from_sheet:
        headers = sheet_manager.get_users_headers()
        user_dict = dict(zip(headers, user_data_from_sheet))

        if user_dict.get('status') == 'block':
            await update.message.reply_text("К сожалению, твой доступ к боту заблокирован.")
            return ConversationHandler.END

        # Если пользователь полностью зарегистрирован
        if user_dict.get('email_status') == 'Confirmed' and user_dict.get('rules_acknowledged') == 'TRUE':
            context.user_data['in_main_menu'] = True
            await update.message.reply_text("С возвращением! Ты в главном меню.", reply_markup=get_main_menu_keyboard())
            return MAIN_MENU

        # Если не подтвердил почту
        elif user_dict.get('email_status') == 'Pending':
            await update.message.reply_text(
                "С возвращением! Похоже, ты не завершил подтверждение почты.\n\n"
                "Чтобы получить новый код, пожалуйста, введи свой университетский email еще раз.",
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_EMAIL

    # Новая регистрация
    welcome_message = (
        "Добро пожаловать в бот для записи на стирку от Студкома мехмата.\n\n"
        "Для получения доступа к функционалу бота необходимо пройти регистрацию:\n\n"
        "Введи свою фамилию с большой буквы (пример: Иванов):"
    )
    await update.message.reply_text(welcome_message, reply_markup=ReplyKeyboardRemove())
    return AWAITING_SURNAME


@block_check
async def info_command_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает информационные команды (например, /feedback)."""
    command = update.message.text.lstrip('/')
    text = COMMANDS_INFO.get(command, "Извини, информация по этой команде не найдена.")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # Возвращаем пользователя в то же состояние, в котором он был
    # Это позволяет командам работать без прерывания диалога
    if context.user_data.get('in_main_menu'):
        return MAIN_MENU
    return ConversationHandler.END


@block_check
async def help_command(update: Update, context: CallbackContext) -> int:
    """Отправляет справочное сообщение."""
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)
    if context.user_data.get('in_main_menu'):
        return MAIN_MENU
    return ConversationHandler.END


@block_check
async def main_menu_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает кнопки главного меню."""
    text = update.message.text
    if text == 'Записаться на стирку':
        return await booking.start_booking(update, context)
    elif text == 'Мои записи':
        return await history.show_upcoming_bookings(update, context, from_menu=True)
    elif text == 'История записей':
        return await history.show_booking_history(update, context)
    else:
        await update.message.reply_text("Используй, пожалуйста, кнопки.", reply_markup=get_main_menu_keyboard())
        return MAIN_MENU


async def cancel_conversation(update: Update, context: CallbackContext) -> int:
    """Отменяет текущий диалог и возвращает в главное меню."""
    await update.message.reply_text('Действие отменено. Ты возвращен в главное меню.',
                                    reply_markup=get_main_menu_keyboard())
    context.user_data.clear()
    context.user_data['in_main_menu'] = True
    return MAIN_MENU