from app.workers.tasks import _prepare_document_for_ocr, _should_retry


class DummyTaskRequest:
    def __init__(self, retries: int):
        self.retries = retries


class DummyTask:
    def __init__(self, retries: int, max_retries: int):
        self.request = DummyTaskRequest(retries)
        self.max_retries = max_retries


def test_should_retry_returns_true_when_attempts_remaining():
    assert _should_retry(DummyTask(retries=1, max_retries=3)) is True


def test_should_retry_returns_false_when_exhausted():
    assert _should_retry(DummyTask(retries=3, max_retries=3)) is False


def test_prepare_document_for_ocr_returns_image_bytes_for_non_pdf():
    image_bytes = b"fake-image"
    assert _prepare_document_for_ocr(image_bytes, "image/jpeg") == image_bytes
