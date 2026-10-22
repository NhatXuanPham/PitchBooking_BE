import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


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
                "SMTP_USER or SMTP_PASSWORD is not configured. "
                "Skipping actual email sending. Target: %s, Subject: %s",
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

        # Attach text and HTML parts
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

    async def send_password_reset_email(
        self,
        to_email: str,
        username: str,
        reset_link: str,
        token: str,
    ) -> bool:
        subject = "Reset your PitchBooking password"
        text_content = (
            f"Hello {username},\n\n"
            "We received a request to reset your password for your PitchBooking account.\n"
            f"Please click the link below or paste it into your browser to set a new password:\n\n"
            f"{reset_link}\n\n"
            f"Alternatively, you can use this reset token directly in the app:\n{token}\n\n"
            f"This link will expire in {settings.RESET_PASSWORD_TOKEN_EXPIRE_MINUTES} minutes.\n"
            "If you did not request a password reset, you can safely ignore this email.\n\n"
            "Best regards,\nThe PitchBooking Team"
        )

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Reset Password - PitchBooking</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #f4f6f8;
      margin: 0;
      padding: 24px;
      color: #1e293b;
    }}
    .container {{
      max-width: 540px;
      margin: 0 auto;
      background-color: #ffffff;
      border-radius: 12px;
      padding: 32px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }}
    .header {{
      text-align: center;
      margin-bottom: 24px;
    }}
    .title {{
      font-size: 22px;
      font-weight: 700;
      color: #0f172a;
      margin: 0;
    }}
    .content {{
      font-size: 15px;
      line-height: 1.6;
      color: #334155;
    }}
    .button-container {{
      text-align: center;
      margin: 28px 0;
    }}
    .btn {{
      display: inline-block;
      padding: 12px 28px;
      background-color: #10b981;
      color: #ffffff !important;
      text-decoration: none;
      font-weight: 600;
      font-size: 15px;
      border-radius: 8px;
    }}
    .token-box {{
      background-color: #f1f5f9;
      border-radius: 6px;
      padding: 12px;
      font-family: monospace;
      font-size: 13px;
      word-break: break-all;
      margin-top: 16px;
      color: #475569;
    }}
    .footer {{
      margin-top: 32px;
      font-size: 13px;
      color: #94a3b8;
      text-align: center;
      border-top: 1px solid #e2e8f0;
      padding-top: 16px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 class="title">PitchBooking</h1>
    </div>
    <div class="content">
      <p>Hello <strong>{username}</strong>,</p>
      <p>We received a request to reset your password. Click the button below to choose a new password:</p>
      <div class="button-container">
        <a href="{reset_link}" class="btn" target="_blank">Reset Password</a>
      </div>
      <p>This password reset link is valid for <strong>{settings.RESET_PASSWORD_TOKEN_EXPIRE_MINUTES} minutes</strong>. If you did not make this request, you can safely ignore this email.</p>
      <p>If you're using an API or mobile client, here is your raw reset token:</p>
      <div class="token-box">{token}</div>
    </div>
    <div class="footer">
      &copy; PitchBooking. All rights reserved.
    </div>
  </div>
</body>
</html>"""

        return await self.send_email(to_email, subject, html_content, text_content)

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

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Verify your email - PitchBooking</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #f4f6f8;
      margin: 0;
      padding: 24px;
      color: #1e293b;
    }}
    .container {{
      max-width: 520px;
      margin: 0 auto;
      background-color: #ffffff;
      border-radius: 12px;
      padding: 32px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }}
    .header {{
      text-align: center;
      margin-bottom: 24px;
    }}
    .title {{
      font-size: 22px;
      font-weight: 700;
      color: #0f172a;
      margin: 0;
    }}
    .content {{
      font-size: 15px;
      line-height: 1.6;
      color: #334155;
    }}
    .otp-box {{
      text-align: center;
      margin: 28px 0;
      background-color: #f0fdf4;
      border: 1px dashed #22c55e;
      border-radius: 8px;
      padding: 16px;
    }}
    .otp-code {{
      font-size: 32px;
      font-weight: 800;
      letter-spacing: 8px;
      color: #15803d;
      font-family: monospace;
    }}
    .footer {{
      margin-top: 32px;
      font-size: 13px;
      color: #94a3b8;
      text-align: center;
      border-top: 1px solid #e2e8f0;
      padding-top: 16px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 class="title">PitchBooking</h1>
    </div>
    <div class="content">
      <p>Hello <strong>{username}</strong>,</p>
      <p>Thank you for registering. Use the 6-digit verification code below to verify your email address:</p>
      <div class="otp-box">
        <div class="otp-code">{otp}</div>
      </div>
      <p>This code will expire in <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>. For your security, do not share this code with anyone.</p>
    </div>
    <div class="footer">
      &copy; PitchBooking. All rights reserved.
    </div>
  </div>
</body>
</html>"""

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

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Reset Password - PitchBooking</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #f4f6f8;
      margin: 0;
      padding: 24px;
      color: #1e293b;
    }}
    .container {{
      max-width: 520px;
      margin: 0 auto;
      background-color: #ffffff;
      border-radius: 12px;
      padding: 32px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }}
    .header {{
      text-align: center;
      margin-bottom: 24px;
    }}
    .title {{
      font-size: 22px;
      font-weight: 700;
      color: #0f172a;
      margin: 0;
    }}
    .content {{
      font-size: 15px;
      line-height: 1.6;
      color: #334155;
    }}
    .otp-box {{
      text-align: center;
      margin: 28px 0;
      background-color: #fef2f2;
      border: 1px dashed #ef4444;
      border-radius: 8px;
      padding: 16px;
    }}
    .otp-code {{
      font-size: 32px;
      font-weight: 800;
      letter-spacing: 8px;
      color: #b91c1c;
      font-family: monospace;
    }}
    .footer {{
      margin-top: 32px;
      font-size: 13px;
      color: #94a3b8;
      text-align: center;
      border-top: 1px solid #e2e8f0;
      padding-top: 16px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 class="title">PitchBooking</h1>
    </div>
    <div class="content">
      <p>Hello <strong>{username}</strong>,</p>
      <p>We received a request to reset your password. Use the 6-digit verification code below to proceed:</p>
      <div class="otp-box">
        <div class="otp-code">{otp}</div>
      </div>
      <p>This code will expire in <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>. If you did not make this request, your account is safe and you can ignore this email.</p>
    </div>
    <div class="footer">
      &copy; PitchBooking. All rights reserved.
    </div>
  </div>
</body>
</html>"""

        return await self.send_email(to_email, subject, html_content, text_content)


email_service = EmailService()
