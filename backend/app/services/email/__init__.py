# Email service for transactional messages (password reset, etc.)
from app.services.email.email_service import EmailService, get_email_service

__all__ = ["EmailService", "get_email_service"]
