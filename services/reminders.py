import logging
import pytz
from datetime import datetime, timedelta
from telegram.ext import CallbackContext
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


async def _send_reminder(context: CallbackContext):
    """Отправляет одно конкретное напоминание пользователю."""
    job = context.job
    message = (
        f"❗️ <b>Напоминание о записи</b> ❗️\n\n"
        f"Через {job.data['minutes_before']} минут у тебя стирка:\n"
        f"<b>{job.data['slot_text']}</b>"
    )
    await context.bot.send_message(chat_id=job.chat_id, text=message, parse_mode=ParseMode.HTML)
    logger.info(f"Отправлено напоминание за {job.data['minutes_before']} минут пользователю {job.chat_id}")


def schedule_booking_reminders(context: CallbackContext, user_id: int, booking_result: dict):
    """Планирует напоминания о стирке на 60 и 10 минут."""
    if not context.job_queue:
        logger.warning("JobQueue не настроена, напоминания не будут установлены.")
        return

    archive_row_index = booking_result['archive_row_index']
    slot_dt_str = f"{booking_result['slot_date']} {booking_result['start_time']}"

    try:
        moscow_tz = pytz.timezone('Europe/Moscow')
        # Создаем "наивный" объект времени и делаем его "осведомленным" о часовом поясе
        aware_dt = moscow_tz.localize(datetime.strptime(slot_dt_str, '%d.%m.%Y %H:%M'))
        slot_text = f"{booking_result['slot_date']} в {booking_result['start_time']} (Этаж {booking_result['floor']})"

        for mins in [60, 10]:
            reminder_time = aware_dt - timedelta(minutes=mins)
            # Убеждаемся, что не планируем напоминание в прошлом
            if reminder_time > datetime.now(moscow_tz):
                context.job_queue.run_once(
                    _send_reminder,
                    reminder_time,
                    chat_id=user_id,
                    name=f"reminder_{archive_row_index}_{'hour' if mins == 60 else '10min'}",
                    data={'slot_text': slot_text, 'minutes_before': mins}
                )
                logger.info(f"Запланировано напоминание для записи {archive_row_index} на {reminder_time}")

    except Exception as e:
        logger.error(f"Ошибка при планировании напоминания для записи {archive_row_index}: {e}")


def remove_reminders(context: CallbackContext, archive_row_index: int):
    """Удаляет все запланированные напоминания для конкретной записи."""
    if not context.job_queue:
        return

    for suffix in ['hour', '10min']:
        job_name = f"reminder_{archive_row_index}_{suffix}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        if not current_jobs:
            continue
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Удалено напоминание: {job.name}")