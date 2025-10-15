import logging

from telegram import BotCommand
from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Главные объекты бота из нашего "ядра"
from core.loader import application

# Импортируем все наши хендлеры
from handlers import common
from handlers.user import registration, booking, history

# Импортируем все состояния
from utils.states import *


# --- Команды бота для меню ---
async def set_bot_commands():
    """Устанавливает команды, видимые в меню Telegram."""
    commands = [
        BotCommand("start", "Перезапустить бота / Главное меню"),
        BotCommand("my_bookings", "Мои предстоящие записи"),
        BotCommand("history", "История моих записей"),
        BotCommand("feedback", "Обратная связь"),
        BotCommand("help", "Помощь по командам бота"),
    ]
    await application.bot.set_my_commands(commands)
    logging.info("Команды бота успешно установлены.")


def main() -> None:
    """Главная функция, которая собирает и запускает бота."""

    # Привязываем функцию установки команд к запуску бота
    application.post_init = set_bot_commands

    # Создаем ConversationHandler, который управляет всеми диалогами
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', common.start),
            CommandHandler('help', common.help_command),
            CommandHandler('feedback', common.info_command_handler),
            CommandHandler("my_bookings", history.show_upcoming_bookings),
            CommandHandler("history", history.show_booking_history),
            # Обработчик для кнопок главного меню, если пользователь уже в нем
            MessageHandler(filters.TEXT & ~filters.COMMAND, common.main_menu_handler)
        ],
        states={
            # --- Состояния регистрации ---
            AWAITING_SURNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.ask_surname)],
            AWAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.ask_name)],
            AWAITING_PATRONYMIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.ask_patronymic)],
            AWAITING_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.ask_dob)],
            AWAITING_ROOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.ask_room)],
            AWAITING_REG_CONFIRMATION: [CallbackQueryHandler(registration.registration_confirmation)],
            AWAITING_EMAIL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lambda u, c: registration.ask_email_and_send_code(u, c, initial=True)
                )
            ],
            AWAITING_EMAIL_CODE: [
                CallbackQueryHandler(registration.resend_code, pattern='^resend_code$'),
                CallbackQueryHandler(registration.prompt_change_email, pattern='^change_email$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration.email_verification)
            ],
            AWAITING_RULES_ACK: [CallbackQueryHandler(registration.rules_ack)],

            # --- Главное меню ---
            MAIN_MENU: [
                CommandHandler('help', common.help_command),
                CommandHandler('feedback', common.info_command_handler),
                CommandHandler("my_bookings", history.show_upcoming_bookings),
                CommandHandler("history", history.show_booking_history),
                MessageHandler(filters.TEXT & ~filters.COMMAND, common.main_menu_handler)
            ],

            # --- Состояния бронирования ---
            BOOKING_FILTER_SETUP: [CallbackQueryHandler(booking.booking_filters_handler)],
            VIEWING_SLOTS: [
                CallbackQueryHandler(booking.handle_pagination, pattern='^page_'),
                CallbackQueryHandler(booking.select_slot, pattern='^slot_'),
                CallbackQueryHandler(booking.back_to_filters_handler, pattern='^filter_back$'),
            ],
            AWAITING_SLOT_CONFIRMATION: [
                CallbackQueryHandler(booking.confirm_booking, pattern='^confirm_book_'),
                CallbackQueryHandler(booking.back_to_slots_handler, pattern='^back_to_slots$')
            ],

            # --- Состояния просмотра и отмены записей ---
            VIEWING_HISTORY: [
                CallbackQueryHandler(history.prompt_cancel_confirmation, pattern='^cancel_'),
                CallbackQueryHandler(history.back_to_main_menu_handler, pattern='^back_to_main_menu_from_bookings$')
            ],
            AWAITING_CANCEL_CONFIRMATION: [
                CallbackQueryHandler(history.confirm_cancellation, pattern='^confirm_cancel_'),
                CallbackQueryHandler(history.show_upcoming_bookings, pattern='^back_to_upcoming$')
            ]
        },
        fallbacks=[
            CommandHandler('start', common.start),
            CommandHandler('cancel', common.cancel_conversation)
        ],
        persistent=True,
        name="main_conversation",
        per_message=False,
    )

    # Регистрируем наш ConversationHandler в приложении
    application.add_handler(conv_handler)

    # Запускаем бота
    logging.info("Бот запущен...")
    application.run_polling()


if __name__ == '__main__':
    main()