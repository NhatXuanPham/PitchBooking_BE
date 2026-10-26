import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_otp_html(
    title: str,
    username: str,
    description: str,
    otp: str,
    is_reset: bool = False,
) -> str:
    box_bg = "#fef2f2" if is_reset else "#f0fdf4"
    box_border = "#ef4444" if is_reset else "#22c55e"
    code_color = "#b91c1c" if is_reset else "#15803d"
    warning = (
        "If you did not make this request, your account is safe and you can ignore this email."
        if is_reset
        else "For your security, do not share this code with anyone."
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title} - PitchBooking</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 24px; color: #1e293b; }}
    .container {{ max-width: 520px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
    .title {{ font-size: 22px; font-weight: 700; color: #0f172a; margin: 0; text-align: center; margin-bottom: 24px; }}
    .content {{ font-size: 15px; line-height: 1.6; color: #334155; }}
    .otp-box {{ text-align: center; margin: 28px 0; background-color: {box_bg}; border: 1px dashed {box_border}; border-radius: 8px; padding: 16px; }}
    .otp-code {{ font-size: 32px; font-weight: 800; letter-spacing: 8px; color: {code_color}; font-family: monospace; }}
    .footer {{ margin-top: 32px; font-size: 13px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="container">
    <h1 class="title">PitchBooking</h1>
    <div class="content">
      <p>Hello <strong>{username}</strong>,</p>
      <p>{description}</p>
      <div class="otp-box"><div class="otp-code">{otp}</div></div>
      <p>This code will expire in <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>. {warning}</p>
    </div>
    <div class="footer">&copy; PitchBooking. All rights reserved.</div>
  </div>
</body>
</html>"""


class EmailService:
    def _send_smtp_email_sync(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> bool:
        if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            logger.warning(
                "SMTP not configured. Skipping email sending. Target: %s, Subject: %s",
                to_email,
                subject,
            )
            return False

        from_email = settings.EMAILS_FROM_EMAIL or settings.SMTP_USER
        from_header = (
            f"{settings.EMAILS_FROM_NAME} <{from_email}>"
            if settings.EMAILS_FROM_NAME
            else from_email
        )

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = from_header
        message["To"] = to_email

        if text_content:
            message.attach(MIMEText(text_content, "plain", "utf-8"))
        message.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            if settings.SMTP_SSL:
                with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(message)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                    server.ehlo()
                    if settings.SMTP_TLS:
                        server.starttls()
                        server.ehlo()
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(message)
            logger.info("Email sent successfully to %s", to_email)
            return True
        except Exception as e:
            logger.error("Failed to send email to %s: %s", to_email, str(e))
            raise e

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._send_smtp_email_sync,
            to_email,
            subject,
            html_content,
            text_content,
        )

    async def send_registration_otp_email(
        self,
        to_email: str,
        username: str,
        otp: str,
    ) -> bool:
        subject = f"{otp} is your PitchBooking verification code"
        text_content = (
            f"Hello {username},\n\n"
            f"Your verification code is: {otp}\n\n"
            f"This code will expire in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
            "If you did not create a PitchBooking account, please ignore this email.\n\n"
            "Best regards,\nThe PitchBooking Team"
        )
        html_content = _build_otp_html(
            title="Verify your email",
            username=username,
            description="Thank you for registering. Use the 6-digit verification code below to verify your email address:",
            otp=otp,
            is_reset=False,
        )
        return await self.send_email(to_email, subject, html_content, text_content)

    async def send_password_reset_otp_email(
        self,
        to_email: str,
        username: str,
        otp: str,
    ) -> bool:
        subject = f"{otp} is your PitchBooking password reset code"
        text_content = (
            f"Hello {username},\n\n"
            f"Your password reset code is: {otp}\n\n"
            f"This code will expire in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
            "If you did not request a password reset, please ignore this email.\n\n"
            "Best regards,\nThe PitchBooking Team"
        )
        html_content = _build_otp_html(
            title="Reset Password",
            username=username,
            description="We received a request to reset your password. Use the 6-digit verification code below to proceed:",
            otp=otp,
            is_reset=True,
        )
        return await self.send_email(to_email, subject, html_content, text_content)


email_service = EmailService()
