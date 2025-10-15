import smtplib
import os
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

def send_verification_email(recipient_email: str, code: str) -> bool:
    smtp_server = os.getenv('SMTP_SERVER')

    try:
        smtp_port = int(os.getenv('SMTP_PORT', 465))
    except (ValueError, TypeError):
        smtp_port = 465  # Порт по умолчанию для безопасного соединения SMTP_SSL

    sender_email = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASSWORD')

    if not all([smtp_server, sender_email, password]):
        print("Ошибка: не все SMTP переменные окружения установлены.")
        return False

    subject = f"[{code}] Код подтверждения для телеграм-бота Studcom Wash"
    body = f"""
    Привет!

    Твой код для подтверждения почты в телеграм-боте: {code}

    Если вы не запрашивали этот код, просто проигнорируйте это письмо.
    """

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    sender_name = "Стирка ДСЛ | Студком мехмата"
    msg['From'] = formataddr((str(Header(sender_name, 'utf-8')), sender_email))
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, [recipient_email], msg.as_string())

        print(f"Письмо успешно отправлено на {recipient_email}")
        return True
    except Exception as e:
        print(f"Ошибка при отправке письма: {e}")
        return False

