from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode

from .bot_commands import COMMANDS_INFO, HELP_MESSAGE
from core.loader import sheet_manager
from utils.decorators import block_check
from utils.messages import WELCOME_BACK, WELCOME_MESSAGE, ASK_SURNAME, EMAIL_PENDING, MAIN_MENU_USER_CHATING, \
    CANCEL_MESSAGE
from utils.states import MAIN_MENU, AWAITING_SURNAME, AWAITING_EMAIL
from keyboards.reply import get_main_menu_keyboard

# Импортируем хендлеры из других файлов, чтобы передавать управление
from .user.registration import ask_email_and_send_code
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

        # Если пользователь полностью зарегистрирован
        if user_dict.get('email_status') == 'Confirmed' and user_dict.get('rules_acknowledged') == 'TRUE' \
                and user_dict.get('status') == 'ok':
            context.user_data['in_main_menu'] = True
            await update.message.reply_text(WELCOME_BACK, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
            return MAIN_MENU

        # Если указал почту, но не подтвердил код
        elif user_dict.get('email_status') == 'Send' and user_dict.get('email'):
            return await ask_email_and_send_code(update, context, initial=False)

        # Если не указал еще почту
        elif user_dict.get('email_status') == 'Pending' or user_dict.get('email_status') == 'Send':
            await update.message.reply_text(EMAIL_PENDING, reply_markup=ReplyKeyboardRemove(),
                                            parse_mode=ParseMode.HTML)
            return AWAITING_EMAIL


    # Новая регистрация
    await update.message.reply_text(WELCOME_MESSAGE, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
    await update.message.reply_text(ASK_SURNAME, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)

    return AWAITING_SURNAME


@block_check
async def info_command_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает информационные команды (например, /feedback)."""
    command = update.message.text.lstrip('/')
    text = COMMANDS_INFO.get(command, "Извини, информация по этой команде не найдена.")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

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
        await update.message.reply_text(MAIN_MENU_USER_CHATING, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
        return MAIN_MENU


async def cancel_conversation(update: Update, context: CallbackContext) -> int:
    """Отменяет текущий диалог и возвращает в главное меню."""
    await update.message.reply_text(CANCEL_MESSAGE, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
    context.user_data.clear()
    context.user_data['in_main_menu'] = True
    return MAIN_MENU