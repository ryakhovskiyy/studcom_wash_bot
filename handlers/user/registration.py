import logging
import random
import re
import time
from datetime import datetime

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext
from telegram.constants import ParseMode

from core.loader import sheet_manager
from keyboards.inline import get_keyboard_summary, get_keyboard_email, get_keyboard_rules
from services.email_service import send_verification_email
from keyboards.reply import get_main_menu_keyboard, get_start_begin_keyboard
from utils.states import *
from utils.messages import (ASK_NAME, ASK_PATRONYMIC, ASK_DOB, ASK_DOB_WRONG, ASK_ROOM,
                            get_registration_summary, EMAIL_ASK, REREGESTRATION_MESSAGE,
                            CHANGE_EMAIL, EMAIL_NOT_MSU, EMAIL_NOT_UNIQUE, EMAIL_NOT_FOUND, EMAIL_ATTEMPTS_3,
                            EMAIL_ATTEMPTS_OFTEN, get_text_after_send_code, EMAIL_SEND_ERROR, EMAIL_CONFIRMED,
                            RULES_CONFIRMATION, EMAIL_CODE_WRONG, RULES_CONFIRMED, MAIN_MENU_MESSAGE)

logger = logging.getLogger(__name__)

async def ask_surname(update: Update, context: CallbackContext) -> int:
    context.user_data['surname'] = update.message.text
    await update.message.reply_text(ASK_NAME, reply_markup=get_start_begin_keyboard(), parse_mode=ParseMode.HTML)
    return AWAITING_NAME

async def ask_name(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    if text == 'Начать заново':
        context.user_data.clear()
        await update.message.reply_text(REREGESTRATION_MESSAGE, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
        return AWAITING_SURNAME
    context.user_data['first_name'] = text
    await update.message.reply_text(ASK_PATRONYMIC, reply_markup=get_start_begin_keyboard(skip=True), parse_mode=ParseMode.HTML)
    return AWAITING_PATRONYMIC

async def ask_patronymic(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    if text == 'Начать заново':
        context.user_data.clear()
        await update.message.reply_text(REREGESTRATION_MESSAGE, reply_markup=ReplyKeyboardRemove(),
                                        parse_mode=ParseMode.HTML)
        return AWAITING_SURNAME
    context.user_data['patronymic'] = '' if text == 'Пропустить' else text
    await update.message.reply_text(ASK_DOB, reply_markup=get_start_begin_keyboard(), parse_mode=ParseMode.HTML)
    return AWAITING_DOB

async def ask_dob(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    if text == 'Начать заново':
        context.user_data.clear()
        await update.message.reply_text(REREGESTRATION_MESSAGE, reply_markup=ReplyKeyboardRemove(),
                                        parse_mode=ParseMode.HTML)
        return AWAITING_SURNAME
    try:
        dob = text
        datetime.strptime(dob, '%d.%m.%Y')
        context.user_data['date_of_birth'] = dob
        await update.message.reply_text(ASK_ROOM, reply_markup=get_start_begin_keyboard(), parse_mode=ParseMode.HTML)
        return AWAITING_ROOM
    except ValueError:
        await update.message.reply_text(ASK_DOB_WRONG, reply_markup=get_start_begin_keyboard(), parse_mode=ParseMode.HTML)
        return AWAITING_DOB

async def ask_room(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    if text == 'Начать заново':
        context.user_data.clear()
        await update.message.reply_text(REREGESTRATION_MESSAGE, reply_markup=ReplyKeyboardRemove(),
                                        parse_mode=ParseMode.HTML)
        return AWAITING_SURNAME
    context.user_data['room_number'] = text
    await update.message.reply_text(get_registration_summary(context.user_data), reply_markup=get_keyboard_summary(), parse_mode=ParseMode.HTML)
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

        await query.edit_message_text(EMAIL_ASK, parse_mode=ParseMode.HTML)
        return AWAITING_EMAIL
    else:
        context.user_data.clear()
        await query.edit_message_text(REREGESTRATION_MESSAGE, parse_mode=ParseMode.HTML)
        return AWAITING_SURNAME

async def prompt_change_email(update: Update, context: CallbackContext) -> int:
    """Обрабатывает кнопку 'Ввести другую почту'."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(CHANGE_EMAIL, parse_mode=ParseMode.HTML)
    return AWAITING_EMAIL

async def ask_email_and_send_code(update: Update, context: CallbackContext, initial: bool = True):
    """Централизованная функция для запроса email и отправки кода."""
    message_source = update.effective_message

    if initial:
        email = update.message.text
        if not re.match(r"[^@]+@math\.msu\.ru$", email):
            await update.message.reply_text(EMAIL_NOT_MSU, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
            return AWAITING_EMAIL

        user_id = update.effective_user.id
        if sheet_manager.is_email_registered(email, user_id):
            await update.message.reply_text(EMAIL_NOT_UNIQUE, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
            return AWAITING_EMAIL

        context.user_data['email'] = email
        sheet_manager.update_user_field(user_id, 'email', email)
    else:
        email = context.user_data.get('email')
        if not email:
            await message_source.reply_text(EMAIL_NOT_FOUND, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)
            return AWAITING_EMAIL

    now = time.time()
    context.user_data.setdefault('email_attempts', [])
    context.user_data['email_attempts'] = [t for t in context.user_data['email_attempts'] if now - t < 1800]


    if len(context.user_data['email_attempts']) >= 3:
        await message_source.reply_text(EMAIL_ATTEMPTS_3, reply_markup=get_keyboard_email(), parse_mode=ParseMode.HTML)
        return AWAITING_EMAIL_CODE

    if context.user_data['email_attempts'] and (now - context.user_data['email_attempts'][-1] < 60):
        await message_source.reply_text(EMAIL_ATTEMPTS_OFTEN, reply_markup=get_keyboard_email(), parse_mode=ParseMode.HTML)
        return AWAITING_EMAIL_CODE

    code = str(random.randint(100000, 999999))
    context.user_data['verification_code'] = code

    if send_verification_email(email, code):
        context.user_data['email_attempts'].append(now)
        sheet_manager.update_user_field(update.effective_user.id, 'email_status', 'Send')

        if update.callback_query:
            await update.callback_query.answer("Новый код отправлен!", show_alert=False)
            await update.callback_query.edit_message_text(get_text_after_send_code(email), reply_markup=get_keyboard_email(), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(get_text_after_send_code(email), reply_markup=get_keyboard_email(), parse_mode=ParseMode.HTML)
        return AWAITING_EMAIL_CODE
    else:
        await message_source.reply_text(EMAIL_SEND_ERROR, reply_markup=get_keyboard_email(), parse_mode=ParseMode.HTML)
        return AWAITING_EMAIL_CODE

async def resend_code(update: Update, context: CallbackContext) -> int:
    """Обрабатывает нажатие кнопки 'Отправить код еще раз'."""
    return await ask_email_and_send_code(update, context, initial=False)

async def email_verification(update: Update, context: CallbackContext) -> int:
    user_code = update.message.text
    if user_code == context.user_data.get('verification_code'):
        user_id = update.effective_user.id
        email = context.user_data['email']
        sheet_manager.update_user_field(user_id, 'email', email)
        sheet_manager.update_user_field(user_id, 'email_status', 'Confirmed')

        memo_image_path = "media/memo.jpg"
        rules_path = "documents/rules.pdf"

        await update.message.reply_text(EMAIL_CONFIRMED, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML)

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

        await update.message.reply_text(RULES_CONFIRMATION, reply_markup=get_keyboard_rules(), parse_mode=ParseMode.HTML)
        return AWAITING_RULES_ACK
    else:
        await update.message.reply_text(EMAIL_CODE_WRONG, reply_markup=get_keyboard_email(), parse_mode=ParseMode.HTML)
        return AWAITING_EMAIL_CODE

async def rules_ack(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == 'rules_accepted':
        user_id = update.effective_user.id
        sheet_manager.update_user_field(update.effective_user.id, 'rules_acknowledged', 'TRUE')
        sheet_manager.update_user_field(user_id, 'status', 'ok')

        await query.edit_message_text(RULES_CONFIRMED, reply_markup=None, parse_mode=ParseMode.HTML)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=MAIN_MENU_MESSAGE,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )
        context.user_data.clear()
        context.user_data['in_main_menu'] = True
        return MAIN_MENU
    return AWAITING_RULES_ACK