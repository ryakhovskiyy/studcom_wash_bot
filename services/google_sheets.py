import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import logging
import pytz
from datetime import datetime

logger = logging.getLogger(__name__)

class SheetManager:
    def __init__(self):
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

        service_account_file = os.getenv('SERVICE_ACCOUNT_FILE', 'credentials.json')
        sheet_name = os.getenv('SHEET_NAME')
        if not sheet_name:
            raise ValueError("Переменная SHEET_NAME должна быть установлена в .env")

        creds = ServiceAccountCredentials.from_json_keyfile_name(service_account_file, scope)
        client = gspread.authorize(creds)

        self.users_sheet = client.open(sheet_name).worksheet("users")
        self.schedule_sheet = client.open(sheet_name).worksheet("schedule")
        self.archive_sheet = client.open(sheet_name).worksheet("archive")
        self.config_sheet = client.open(sheet_name).worksheet("config")
        self._users_headers = self.users_sheet.row_values(1)
        self._schedule_headers = self.schedule_sheet.row_values(1)
        self._archive_headers = self.archive_sheet.row_values(1)

    def get_users_headers(self):
        return self._users_headers

    def get_schedule_headers(self):
        return self._schedule_headers

    def get_config(self) -> dict:
        """Получаем словарь старост, их контактов, комнат и тд."""
        try:
            return {row['key']: row['value'] for row in self.config_sheet.get_all_records()}
        except Exception as e:
            logger.critical(f"Ошибка при загрузке конфигурации: {e}")
            return {}

    def get_user(self, telegram_id: int):
        """Получаем данные о пользователе по его telegram_id."""
        try:
            cell = self.users_sheet.find(str(telegram_id), in_column=1)
            return self.users_sheet.row_values(cell.row)
        except gspread.CellNotFound:
            return None

    def add_user(self, user_data: dict):
        """Добавляем нового/обновляем существующего пользователя."""
        telegram_id = str(user_data['telegram_id'])
        row_to_add = [user_data.get(header, '') for header in self._users_headers]

        if 'email_status' in self._users_headers:
            idx = self._users_headers.index('email_status')
            row_to_add[idx] = 'Pending'

        try:
            cell = self.users_sheet.find(telegram_id, in_column=1)
            if cell:
                self.users_sheet.update(f'A{cell.row}', [row_to_add])
            else:
                self.users_sheet.append_row(row_to_add)
        except gspread.CellNotFound:
            self.users_sheet.append_row(row_to_add)

    def update_user_field(self, telegram_id: int, field_name: str, value: str):
        """Обновляем конкретное поле у конкретного пользователя."""
        try:
            cell = self.users_sheet.find(str(telegram_id), in_column=1)
            col_index = self._users_headers.index(field_name) + 1
            self.users_sheet.update_cell(cell.row, col_index, value)
            # logger.info(f"Успешно обновлено поле '{field_name}' для {telegram_id}")
        except (gspread.CellNotFound, ValueError) as e:
            logger.error(f"Ошибка при обновлении поля '{field_name}' для {telegram_id}: {e}")

    def is_email_registered(self, email: str, current_user_id: int) -> bool:
        """Проверяет, подтвержден ли email на ДРУГОГО пользователя."""
        try:
            email_col_index = self._users_headers.index('email') + 1
            status_col_index = self._users_headers.index('email_status') + 1

            # Находим все ячейки с таким email
            cells = self.users_sheet.findall(email, in_column=email_col_index)

            for cell in cells:
                user_id_in_row = self.users_sheet.cell(cell.row, 1).value
                # Проверяем, что это не текущий пользователь
                if str(user_id_in_row) != str(current_user_id):
                    # А теперь проверяем статус этого другого пользователя
                    email_status_in_row = self.users_sheet.cell(cell.row, status_col_index).value
                    if email_status_in_row == 'Confirmed':
                        return True  # Email занят и подтвержден другим!

            return False  # Email свободен или принадлежит текущему пользователю
        except (gspread.exceptions.CellNotFound, ValueError):
            return False

    def is_user_blocked(self, telegram_id: int) -> bool:
        """Проверяет, установлен ли у пользователя статус 'block'."""
        try:
            user_row = self.get_user(telegram_id)
            if user_row:
                user_dict = dict(zip(self._users_headers, user_row))
                return user_dict.get('status') == 'block'
            return False  # Если пользователь не найден, он не заблокирован
        except Exception:
            return False

    def get_unique_column_values(self, sheet_name: str, column_name: str) -> list:
        """
        Возвращает отсортированный список уникальных значений из указанного столбца,
        учитывая только те слоты, которые еще не прошли.
        """
        # Бесполезная конструкция, но задел под будущее, если понадобится такая функция и для других таблиц
        sheet = self.schedule_sheet if sheet_name == 'schedule' else None
        if not sheet:
            logger.error("Функция get_unique_column_values() получила неправильное sheet_name")
            return []

        all_records = sheet.get_all_records()

        future_values = set()
        # Устанавливаем московское время для корректного сравнения слотов
        moscow_tz = pytz.timezone('Europe/Moscow')
        now_aware = datetime.now(moscow_tz)

        for record in all_records:
            try:
                # Собираем полную дату и время слота, чтобы проверить, не в прошлом ли он
                slot_datetime_str = f"{record.get('slot_date')} {record.get('start_time')}"
                slot_datetime_naive = datetime.strptime(slot_datetime_str, '%d.%m.%Y %H:%M')
                slot_datetime_aware = moscow_tz.localize(slot_datetime_naive)

                # Если слот еще не прошел
                if slot_datetime_aware > now_aware:
                    # Получаем значение из нужного нам столбца (например, 'floor' или 'slot_date')
                    value = record.get(column_name)
                    if value:
                        future_values.add(str(value))
            except (ValueError, KeyError):
                # Игнорируем строки с неправильным форматом даты или времени
                continue

        # Сортируем и возвращаем уникальные значения только из будущих слотов
        return sorted(list(future_values))

    def get_available_slots(self, filters: dict) -> list:
        """
            Возвращает отсортированный список доступных слотов, учитывая только те слоты,
            которые еще не прошли и удовлетворяют всем фильтрам пользователя.
        """
        all_slots = self.schedule_sheet.get_all_records()
        available = []

        moscow_tz = pytz.timezone('Europe/Moscow')
        now_aware = datetime.now(moscow_tz)

        selected_times = filters.get('times', [])

        for i, slot in enumerate(all_slots):
            try:
                # Собираем полную дату и время слота в один объект
                slot_datetime_str = f"{slot['slot_date']} {slot['start_time']}"
                slot_datetime_naive = datetime.strptime(slot_datetime_str, '%d.%m.%Y %H:%M')
                slot_datetime_aware = moscow_tz.localize(slot_datetime_naive)

                # Пропускаем слот, если его время уже прошло
                if slot_datetime_aware < now_aware:
                    continue
            except (ValueError, KeyError):
                # Пропускаем строки с некорректным форматом даты или времени
                continue

            if filters.get('dates') and slot['slot_date'] not in filters['dates']:
                continue
            if filters.get('floors') and str(slot['floor']) not in filters['floors']:
                continue

            if selected_times:
                time_h = int(slot['start_time'].split(':')[0])
                time_match = False
                if 'Утро' in selected_times and (4 <= time_h < 12): time_match = True
                if not time_match and 'День' in selected_times and (12 <= time_h < 18): time_match = True
                if not time_match and 'Вечер' in selected_times and (18 <= time_h <= 23 or 0 <= time_h < 4): time_match = True
                if not time_match: continue

            slot['row_index'] = i + 2
            available.append(slot)

        available.sort(key=lambda x: (datetime.strptime(x['slot_date'], '%d.%m.%Y'), x['start_time'].zfill(5)))
        return available

    def get_user_bookings(self, telegram_id: int, upcoming_only: bool = True) -> list:
        """
            Возвращает все записи пользователя с tg-id равным telegram_id.
            Если upcoming_only == True, то вернет слоты, которые еще не начались и имеют статус 'Booked',
            это нужно для корректной работы /my_bookings и отмены записи.
            Если upcoming_only == False, то вернет все слоты пользователя, это нужно для работы /history.
        """
        all_bookings = self.archive_sheet.get_all_records()
        user_bookings = []

        moscow_tz = pytz.timezone('Europe/Moscow')
        now_aware = datetime.now(moscow_tz)

        for i, booking in enumerate(all_bookings):
            if str(booking.get('telegram_id')) == str(telegram_id):
                if not booking.get('slot_date'):
                    continue
                if upcoming_only:
                    try:
                        slot_datetime_str = f"{booking['slot_date']} {booking['start_time']}"
                        slot_datetime_naive = datetime.strptime(slot_datetime_str, '%d.%m.%Y %H:%M')
                        slot_datetime_aware = moscow_tz.localize(slot_datetime_naive)

                        if slot_datetime_aware > now_aware and booking.get('status') == 'Booked':
                            booking['archive_row_index'] = i + 2
                            user_bookings.append(booking)
                    except (ValueError, KeyError):
                        continue
                else:
                    booking['archive_row_index'] = i + 2
                    user_bookings.append(booking)

        # старая сортировка по дате/времени самих слотов:
        # user_bookings.sort(key=lambda x: (datetime.strptime(x['slot_date'], '%d.%m.%Y'), x['start_time'].zfill(5)), reverse=True)
        # новая сортировка по booking_timestamp (времени бронирования):
        user_bookings.sort(key=lambda x: (datetime.strptime(x['booking_timestamp'], '%d.%m.%Y %H:%M')), reverse=True)
        return user_bookings

    def book_slot(self, slot_data: dict, user_info: dict) -> dict | None:
        """Бронирует слот, добавляя ФИО и ответственного в архив. Возвращает словарь с данными о брони."""
        try:
            user_id = user_info['id']
            user_row = self.get_user(user_id)
            full_name = "Не найден в 'users'"

            if user_row:
                user_dict = dict(zip(self._users_headers, user_row))
                surname = user_dict.get('surname', '')
                first_name = user_dict.get('first_name', '')
                patronymic = user_dict.get('patronymic', '')
                full_name = f"{surname} {first_name} {patronymic}".strip()

            new_archive_row_index = len(self.archive_sheet.get_all_values()) + 1

            # Собираем строку для архива, включая ответственного и ФИО
            moscow_tz = pytz.timezone('Europe/Moscow')
            archive_row = {header: slot_data.get(header, '') for header in self._archive_headers}
            archive_row.update({
                'telegram_id': user_info['id'],
                'username': user_info['username'],
                'full_name': full_name,
                'booking_timestamp': datetime.now(moscow_tz).strftime('%d.%m.%Y %H:%M'),
                'status': 'Booked'
            })

            target_row_index = slot_data['row_index']

            actual_slot_data_row = self.schedule_sheet.row_values(target_row_index)
            if not actual_slot_data_row:
                logger.warning(f"Гонка_1: Строка {target_row_index} удалена (была последней)")
                return None

            actual_slot_data = dict(zip(self._schedule_headers, actual_slot_data_row))

            if actual_slot_data.get('slot_date')!= slot_data.get('slot_date') or \
                    actual_slot_data.get('start_time') != slot_data.get('start_time') or \
                    actual_slot_data.get('floor') != slot_data.get('floor'):
                logger.warning(
                    f"Гонка_2: Строка {target_row_index} сместилась! "
                    f"Ожидали: {slot_data.get('slot_date')} {slot_data.get('start_time')} эт.{slot_data.get('floor')}. "
                    f"Получили: {actual_slot_data.get('slot_date')} {actual_slot_data.get('start_time')} эт.{actual_slot_data.get('floor')}"
                )
                return None

            self.archive_sheet.append_row([archive_row.get(h, '') for h in self._archive_headers])
            self.schedule_sheet.delete_rows(target_row_index)

            return {'archive_row_index': new_archive_row_index, 'full_name': full_name, **actual_slot_data}

        except (gspread.exceptions.APIError, gspread.exceptions.CellNotFound, IndexError) as e:
            logger.error(
                f"Критическая ошибка при бронировании (row_index: {slot_data.get('row_index')})! "
                f"User: {user_info.get('id')}. Ошибка: {e}"
            )
            return None

    def cancel_booking(self, archive_row_index: int) -> bool:
        """Отменяет бронь: возвращает слот в schedule и меняет статус в archive."""
        try:
            booking_to_cancel = dict(zip(self._archive_headers, self.archive_sheet.row_values(archive_row_index)))
            if booking_to_cancel.get('status') != 'Booked':
                return False

            slot_to_return = [booking_to_cancel.get(header, '') for header in self._schedule_headers]

            self.schedule_sheet.append_row(slot_to_return)

            status_col_index = self._archive_headers.index('status') + 1
            self.archive_sheet.update_cell(archive_row_index, status_col_index, 'Canceled')

            return True
        except (gspread.exceptions.APIError, ValueError, IndexError) as e:
            logger.error(f"Критическая ошибка при отмене бронировании (row_index: {archive_row_index}): {e}")
            return False