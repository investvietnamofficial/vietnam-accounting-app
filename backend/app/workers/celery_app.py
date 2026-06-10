"""
Celery async workers for background document processing.

Task flow:
  upload → process_document_task → OCR → extract_fields → update DB → notify
"""

import logging

try:
    from celery import Celery
except ImportError:
    Celery = None

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class _NoopCelery:
    def task(self, *args, **kwargs):
        def decorator(func):
            func.delay = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Celery is not installed"))
            return func
        return decorator


if Celery is None:
    celery_app = _NoopCelery()
else:
    celery_app = Celery(
        "vn_accounting",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.workers.tasks"],
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Ho_Chi_Minh",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_routes={
            "app.workers.tasks.process_document": {"queue": "ocr"},
            "app.workers.tasks.send_notification": {"queue": "notifications"},
        },
    )
