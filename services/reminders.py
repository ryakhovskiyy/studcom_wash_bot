import logging
import pytz
from datetime import datetime, timedelta
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from services.google_sheets import SheetManager

logger = logging.getLogger(__name__)

async def _send_reminder(context: CallbackContext):
    """Отправляет напоминание ПОЛЬЗОВАТЕЛЮ."""
    job = context.job
    job_data = job.data

    message = (
        f"❗️ <b>Напоминание о записи</b> ❗️\n\n"
        f"Через {job_data['minutes_before']} минут у тебя стирка:\n"
        f"<b>{job_data['slot_text']}</b>"
        f"Перед стиркой нужно взять ключ от постирочной у ответственного в комнате <b>{job_data['key_room']}</b>.\n\n"
        f"<b>Твой ответственный:</b> {job_data['responsible']}\n"
        f"<b>Связь с ответственным:</b> {job_data['contact']}"
    )
    await context.bot.send_message(chat_id=job.chat_id, text=message, parse_mode=ParseMode.HTML)
    logger.info(f"Отправлено напоминание пользователю {job.chat_id}")


async def _send_monitor_reminder(context: CallbackContext):
    """(НОВЫЙ) Отправляет напоминание СТАРОСТЕ."""
    job = context.job
    slot_text = job.data['slot_text']
    full_name = job.data['full_name']
    user_id = job.data['user_id']
    paper_sign = job.data['paper_sign']

    message = (
        f"🔔 <b>Напоминание о записи</b> 🔔\n\n"
        f"Через 10 минут у студента {full_name} {f"(@{user_id})" if user_id else ''} стирка:\n"
        f"<b>{slot_text}</b>\n\n"
        f"Студент {'' if paper_sign == '1' else "<b>НЕ</b>"} расписался в журнале."
    )
    await context.bot.send_message(chat_id=job.chat_id, text=message, parse_mode=ParseMode.HTML)
    logger.info(f"Отправлено напоминание старосте {job.chat_id}")


async def schedule_booking_reminders(context: CallbackContext, user_id: int, full_name: str,
        booking_result: dict, sheet_manager: SheetManager):
    """
    Планирует напоминания для пользователя
    И отправляет уведомления старосте.
    """
    if not context.job_queue:
        logger.warning("JobQueue не настроена, напоминания не будут установлены.")
        return

    archive_row_index = booking_result['archive_row_index']
    slot_dt_str = f"{booking_result['slot_date']} {booking_result['start_time']}"
    slot_text = f"{booking_result['slot_date']} с {booking_result['start_time']} до {booking_result['end_time']} (Этаж {booking_result['floor']})"

    try:
        moscow_tz = pytz.timezone('Europe/Moscow')
        aware_dt = moscow_tz.localize(datetime.strptime(slot_dt_str, '%d.%m.%Y %H:%M'))
        now_aware = datetime.now(moscow_tz)

        config = sheet_manager.get_config()
        responsible_name = booking_result.get('responsible', 'Не назначен')
        config_key_contact = f'responsible_{responsible_name}_contact'
        config_key_room = f'responsible_{responsible_name}_key_room'

        contact = config.get(config_key_contact, 'не указан')
        key_room = config.get(config_key_room, 'не указана')

        # ПЛАНИРУЕМ НАПОМИНАНИЯ ДЛЯ ПОЛЬЗОВАТЕЛЯ:
        for mins in [60, 10]:
            reminder_time = aware_dt - timedelta(minutes=mins)
            if reminder_time > now_aware:
                user_job_data = {
                    'slot_text': slot_text,
                    'minutes_before': mins,
                    'key_room': key_room,
                    'responsible': responsible_name,
                    'contact': contact
                }

                context.job_queue.run_once(
                    _send_reminder,
                    reminder_time,
                    chat_id=user_id,
                    name=f"reminder_{archive_row_index}_{'hour' if mins == 60 else '10min'}",
                    data=user_job_data
                )
                logger.info(f"Запланировано напоминание для {user_id} на {reminder_time}")

        # ОТПРАВЛЯЕМ УВЕДОМЛЕНИЯ СТАРОСТЕ:

        monitor_id = None
        config_key_peer_id = f'responsible_{responsible_name}_peer_id'
        monitor_id_str = config.get(config_key_peer_id)

        if monitor_id_str:
            try:
                monitor_id = int(monitor_id_str)
            except ValueError:
                logger.error(f"Не удалось прочитать peer_id для {responsible_name}. ID в конфиге: {monitor_id_str}")
        else:
            logger.warning(f"Не найден peer_id для старосты {responsible_name} (ключ {config_key_peer_id})")

        # Если нашли ID старосты - отправляем и планируем
        if monitor_id:
            # Отправляем НЕМЕДЛЕННОЕ уведомление о новой брони
            paper_sign = sheet_manager.get_user(user_id).get('paper_sign')
            message_text = (
                f"🔔 <b>Новая запись!</b> 🔔\n\n"
                f"Студент <b>{full_name}</b> (ID: {user_id}) забронировал у вас слот:\n\n"
                f"<b>{slot_text}</b>\n\n"
                f"Студент {'' if paper_sign == '1' else "<b>НЕ</b>"} расписался в журнале."
            )
            try:
                await context.bot.send_message(chat_id=monitor_id, text=message_text, parse_mode=ParseMode.HTML)
                logger.info(f"Отправлено уведомление о брони старосте {responsible_name} (ID: {monitor_id})")
            except Exception as e:
                logger.error(f"Не удалось отправить немедленное уведомление старосте {monitor_id}: {e}")

            # Планируем 10-минутное НАПОМИНАНИЕ для старосты
            reminder_time_10min = aware_dt - timedelta(minutes=10)
            if reminder_time_10min > now_aware:
                job_name = f"monitor_reminder_{archive_row_index}_10min"
                job_data = {'slot_text': slot_text, 'full_name': full_name, 'user_id': user_id, 'paper_sign': paper_sign}

                context.job_queue.run_once(
                    _send_monitor_reminder,
                    reminder_time_10min,
                    chat_id=monitor_id,
                    name=job_name,
                    data=job_data
                )
                logger.info(f"Запланировано напоминание для старосты {monitor_id} на {reminder_time_10min}")

    except Exception as e:
        logger.error(f"Ошибка при планировании напоминания для записи {archive_row_index}: {e}")

def remove_reminders(context: CallbackContext, archive_row_index: int):
    """(ОБНОВЛЕН) Удаляет напоминания для пользователя И старосты."""
    if not context.job_queue:
        return

    # Удаляем напоминания для пользователя
    for suffix in ['hour', '10min']:
        job_name = f"reminder_{archive_row_index}_{suffix}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Удалено напоминание для пользователя: {job.name}")

    # Удаляем напоминания для старосты
    monitor_job_name = f"monitor_reminder_{archive_row_index}_10min"
    current_jobs = context.job_queue.get_jobs_by_name(monitor_job_name)
    for job in current_jobs:
        job.schedule_removal()
        logger.info(f"Удалено напоминание для старосты: {job.name}")