"""
Transactional email service using SMTP.

In production (APP_ENV=production), sends real emails.
In development, logs the email content to the console instead.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import lru_cache

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


class EmailService:
    def __init__(self):
        self.settings = get_settings()

    def _build_reset_email(self, to_email: str, reset_token: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "VN Accounting — Password Reset Request"
        msg["From"] = self.settings.smtp_from or self.settings.smtp_user
        msg["To"] = to_email

        reset_url = f"{self.settings.app_env == 'production' and 'https' or 'http'}://{self.settings.allowed_origins[0].replace('http://', '').replace('https://', '')}/auth/reset-password?token={reset_token}"

        plain = f"""You received this email because a password reset was requested for your VN Accounting account.

If this was you, click the link below to set a new password:
{reset_url}

This link expires in {self.settings.password_reset_token_expire_minutes} minutes.

If you did not request a password reset, you can safely ignore this email.
"""
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#1a1a2e;">VN Accounting — Password Reset</h2>
  <p>You received this email because a password reset was requested for your account.</p>
  <p>If this was you, click the button below:</p>
  <a href="{reset_url}" style="display:inline-block;background:#eab308;color:#000;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;">Reset Password</a>
  <p style="margin-top:20px;font-size:13px;color:#666;">This link expires in {self.settings.password_reset_token_expire_minutes} minutes.<br>If you didn't request this, you can safely ignore this email.</p>
</body>
</html>"""

        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        return msg

    def send_password_reset_email(self, to_email: str, reset_token: str) -> bool:
        """
        Send a password reset email to the given address.
        In dev mode, log instead of sending.
        Returns True on success, False on failure.
        """
        msg = self._build_reset_email(to_email, reset_token)

        if not self.settings.is_production:
            # Dev: log the email, never actually send
            logger.info(
                "email_dev_mode",
                action="password_reset",
                to=to_email,
                subject=msg["Subject"],
                reset_url_template="/auth/reset-password?token=***",
            )
            return True

        if not self.settings.smtp_user or not self.settings.smtp_password:
            logger.warning("smtp_not_configured", action="password_reset", to=to_email)
            return False

        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as server:
                if self.settings.smtp_use_tls:
                    server.starttls()
                server.login(self.settings.smtp_user, self.settings.smtp_password)
                server.sendmail(msg["From"], [to_email], msg.as_string())
            logger.info("email_sent", action="password_reset", to=to_email)
            return True
        except Exception as exc:
            logger.error("email_send_failed", action="password_reset", to=to_email, error=str(exc))
            return False


@lru_cache
def get_email_service() -> EmailService:
    return EmailService()
