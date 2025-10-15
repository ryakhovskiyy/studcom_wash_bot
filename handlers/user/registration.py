import logging
import random
import re
import time
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from telegram.constants import ParseMode
from telegram.error import BadRequest

from core.loader import sheet_manager
from services.email_service import send_verification_email
from keyboards.reply import get_main_menu_keyboard
from utils.states import * # Импортируем все состояния

logger = logging.getLogger(__name__)

async def ask_surname(update: Update, context: CallbackContext) -> int:
    context.user_data['surname'] = update.message.text
    await update.message.reply_text("Теперь введи свое имя с большой буквы (пример: Иван):")
    return AWAITING_NAME

async def ask_name(update: Update, context: CallbackContext) -> int:
    context.user_data['first_name'] = update.message.text
    await update.message.reply_text(
        "Введи свое отчество с большой буквы (пример: Иванович) (если нет, нажми 'Пропустить'):",
        reply_markup=ReplyKeyboardMarkup([['Пропустить']], one_time_keyboard=True,
                                         resize_keyboard=True))
    return AWAITING_PATRONYMIC

async def ask_patronymic(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    context.user_data['patronymic'] = '' if text == 'Пропустить' else text
    await update.message.reply_text("Введи свою дату рождения в формате ДД.ММ.ГГГГ (пример: 31.01.2000):",
                                    reply_markup=ReplyKeyboardRemove())
    return AWAITING_DOB

async def ask_dob(update: Update, context: CallbackContext) -> int:
    dob = update.message.text
    try:
        datetime.strptime(dob, '%d.%m.%Y')
        context.user_data['date_of_birth'] = dob
        await update.message.reply_text("Введи номер своей комнаты (пример: А901):")
        return AWAITING_ROOM
    except ValueError:
        await update.message.reply_text(
            "Неверный формат. Пожалуйста, введи дату в формате ДД.ММ.ГГГГ (пример: 31.01.2000):")
        return AWAITING_DOB

async def ask_room(update: Update, context: CallbackContext) -> int:
    context.user_data['room_number'] = update.message.text
    summary = (
        "Пожалуйста, проверь введенные данные:\n\n"
        f"<b>Фамилия:</b> {context.user_data['surname']}\n"
        f"<b>Имя:</b> {context.user_data['first_name']}\n"
        f"<b>Отчество:</b> {context.user_data.get('patronymic', 'Нет')}\n"
        f"<b>Дата рождения:</b> {context.user_data['date_of_birth']}\n"
        f"<b>Комната:</b> {context.user_data['room_number']}"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Подтвердить", callback_data='confirm_reg'),
        InlineKeyboardButton("🔄 Ввести заново", callback_data='retry_reg')
    ]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return AWAITING_REG_CONFIRMATION

async def registration_confirmation(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if query.data == 'confirm_reg':
        user_info = context.user_data
        user_info['telegram_id'] = user.id
        user_info['username'] = user.username if user.username else ""
        sheet_manager.add_user(user_info)

        await query.edit_message_text(
            "Данные сохранены. Теперь необходимо подтвердить твою почту. "
            "Введи свой университетский email, который оканчивается на @math.msu.ru"
        )
        return AWAITING_EMAIL
    else:
        context.user_data.clear()
        await query.edit_message_text("Давай начнем сначала. Введи свою фамилию с большой буквы (пример: Иванов):")
        return AWAITING_SURNAME

async def prompt_change_email(update: Update, context: CallbackContext) -> int:
    """Обрабатывает кнопку 'Ввести другую почту'."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Пожалуйста, введи новый email-адрес, который оканчивается на @math.msu.ru"
    )
    return AWAITING_EMAIL

async def ask_email_and_send_code(update: Update, context: CallbackContext, initial: bool = True):
    """Централизованная функция для запроса email и отправки кода."""
    message_source = update.effective_message

    if initial:
        email = update.message.text
        if not re.match(r"[^@]+@math\.msu\.ru$", email):
            await update.message.reply_text(
                "Неверный формат почты. Она должна оканчиваться на @math.msu.ru. Попробуй еще раз.")
            return AWAITING_EMAIL

        user_id = update.effective_user.id
        if sheet_manager.is_email_registered(email, user_id):
            await update.message.reply_text("Этот email уже используется другим аккаунтом. Пожалуйста, введи другой.")
            return AWAITING_EMAIL

        context.user_data['email'] = email
    else:
        email = context.user_data.get('email')
        if not email:
            await message_source.reply_text("Произошла ошибка, email не найден. Пожалуйста, введи /start.",
                                            reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

    now = time.time()
    context.user_data.setdefault('email_attempts', [])
    context.user_data['email_attempts'] = [t for t in context.user_data['email_attempts'] if now - t < 1800]

    keyboard = [
        [InlineKeyboardButton("🔄 Отправить код еще раз", callback_data="resend_code")],
        [InlineKeyboardButton("✍️ Ввести другую почту", callback_data="change_email")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if len(context.user_data['email_attempts']) >= 2:
        await message_source.reply_text("Ты слишком часто запрашиваешь код. Пожалуйста, подожди 30 минут.", reply_markup=reply_markup)
        return AWAITING_EMAIL_CODE

    if context.user_data['email_attempts'] and (now - context.user_data['email_attempts'][-1] < 60):
        await message_source.reply_text("Отправлять код можно не чаще раза в минуту. Подожди немного.", reply_markup=reply_markup)
        return AWAITING_EMAIL_CODE

    code = str(random.randint(100000, 999999))
    context.user_data['verification_code'] = code

    if send_verification_email(email, code):
        context.user_data['email_attempts'].append(now)
        message_text = f"На почту {email} отправлен 6-значный код. Введи его для подтверждения."

        if update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        return AWAITING_EMAIL_CODE
    else:
        await message_source.reply_text("Не удалось отправить письмо. Обратись в сообщения группы Студкома мехмата: vk.com/studcom_mm", reply_markup=reply_markup)
        return AWAITING_EMAIL_CODE

async def resend_code(update: Update, context: CallbackContext) -> int:
    """Обрабатывает нажатие кнопки 'Отправить код еще раз'."""
    query = update.callback_query
    await query.answer("Новый код отправлен!", show_alert=False)
    return await ask_email_and_send_code(update, context, initial=False)

async def email_verification(update: Update, context: CallbackContext) -> int:
    user_code = update.message.text
    if user_code == context.user_data.get('verification_code'):
        try:
            await update.message.delete()
        except BadRequest:
            pass

        user_id = update.effective_user.id
        email = context.user_data['email']
        sheet_manager.update_user_field(user_id, 'email', email)
        sheet_manager.update_user_field(user_id, 'email_status', 'Confirmed')

        memo_image_path = "media/memo.jpg"
        rules_path = "documents/rules.pdf"

        await update.message.reply_text(
            f"Почта успешно подтверждена!\n\nТеперь необходимо ознакомиться с правилами использования стиральных машин:")

        with open(memo_image_path, 'rb') as memo_image_file, open(rules_path, 'rb') as rules_file:
            await update.message.reply_photo(
                photo=memo_image_file,
                caption='Гайд по стиральным машинам ДСЛ ⬆️'
            )
            await update.message.reply_document(
                document=rules_file,
                filename='Правила_по_стиральным_машинам_ДСЛ.pdf',
                caption='Правила ⬆️'
            )

        keyboard = [[InlineKeyboardButton("✅ Я ознакомился и принимаю правила", callback_data='rules_accepted')]]
        await update.message.reply_text("Пожалуйста, внимательно прочти гайд и правила, а после подтверди ознакомление:",
                                        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return AWAITING_RULES_ACK
    else:
        await update.message.reply_text("Неверный код. Попробуй еще раз.")
        return AWAITING_EMAIL_CODE

async def rules_ack(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == 'rules_accepted':
        user_id = update.effective_user.id
        sheet_manager.update_user_field(update.effective_user.id, 'rules_acknowledged', 'TRUE')
        sheet_manager.update_user_field(user_id, 'status', 'ok')

        await query.edit_message_text("Отлично! Регистрация завершена.")
        await query.message.reply_text("Ты в главном меню:", reply_markup=get_main_menu_keyboard())
        context.user_data.clear()
        context.user_data['in_main_menu'] = True
        return MAIN_MENU
    return AWAITING_RULES_ACK