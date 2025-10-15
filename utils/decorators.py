from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler

from core.loader import sheet_manager

def block_check(func):
    """Декоратор для проверки, заблокирован ли пользователь."""
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if sheet_manager.is_user_blocked(user_id):
            await update.effective_message.reply_text("К сожалению, твой доступ к боту заблокирован.")
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    return wrapper