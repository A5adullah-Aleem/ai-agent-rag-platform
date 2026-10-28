import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_password_reset_email(to_email: str, reset_url: str) -> None:
    if not all(
        [
            settings.MAIL_USERNAME,
            settings.MAIL_PASSWORD,
            settings.MAIL_FROM,
        ]
    ):
        raise RuntimeError("Email SMTP configuration is missing.")

    message = EmailMessage()
    message["Subject"] = "Reset your NeuralDesk password"
    message["From"] = settings.MAIL_FROM
    message["To"] = to_email

    message.set_content(
        f"""Hello,

We received a request to reset your NeuralDesk password.

Open this link to choose a new password:
{reset_url}

This link expires in 30 minutes and can only be used once.

If you did not request this reset, you can ignore this email.
"""
    )

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.starttls()
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.send_message(message)