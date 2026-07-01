#!/usr/bin/env python3
"""
VN Accounting — Load Test Script (Locust)

Run locally:
    pip install locust
    locust -f backend/scripts/load_test.py \
           --host=http://localhost:8000 \
           --users=50 \
           --spawn-rate=10 \
           --run-time=60s \
           --headless

Or from repo root:
    PYTHONPATH=backend locust -f backend/scripts/load_test.py \
           --host=http://localhost:8000 \
           --users=50 --spawn-rate=10 --run-time=60s --headless

Targeted endpoints:
  - GET  /health          — health check (all users)
  - GET  /api/v1/invoices — invoice list (authenticated users)
  - POST /api/v1/auth/token — login (all users at start for token acquisition)

Metrics to watch:
  - p50 / p95 / p99 response time for /health
  - Error rate on /api/v1/invoices (should be 0% for valid tokens)
  - OCR pipeline throughput if run during a batch upload
"""
from locust import HttpUser, task, between, events
import os

API_HOST = os.getenv("LOCUST_HOST", "http://localhost:8000")

# Static test credentials — replace with real test company user in production
TEST_EMAIL = os.getenv("TEST_USER_EMAIL", "gbert+e2e@test.com")
TEST_PASSWORD = os.getenv("TEST_USER_PASSWORD", "TestPass123456!")


class AnonymousUser(HttpUser):
    """Anonymous user — health check only."""
    wait_time = between(1, 3)

    @task
    def health(self):
        self.client.get("/health")


class AuthenticatedUser(HttpUser):
    """Authenticated user — performs operator workflows."""
    wait_time = between(2, 5)

    def on_start(self):
        """Acquire a JWT token at session start."""
        resp = self.client.post(
            "/api/v1/auth/token",
            data={"username": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10,
        )
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.environment.runner.quit()
            raise RuntimeError(f"Auth failed: {resp.status_code} {resp.text}")

    @task(3)
    def list_invoices(self):
        """List invoices — most common operator action."""
        self.client.get("/api/v1/invoices", headers=self.headers, timeout=10)

    @task(1)
    def list_documents(self):
        """List documents."""
        self.client.get("/api/v1/documents", headers=self.headers, timeout=10)

    @task(1)
    def list_reports(self):
        """List available reports."""
        self.client.get("/api/v1/reports", headers=self.headers, timeout=10)

    @task(1)
    def health_check(self):
        """Internal health check."""
        self.client.get("/health", timeout=5)


# ── Event hooks ──────────────────────────────────────────────────────────────
@events.test_start.add_listener
def on_start(environment, **kwargs):
    print(f"Load test starting against {API_HOST}")
    print(f"Test user: {TEST_EMAIL}")


@events.test_stop.add_listener
def on_stop(environment, **kwargs):
    stats = environment.stats
    print("\n=== Load Test Summary ===")
    print(f"Total requests : {stats.total.num_requests}")
    print(f"Total failures : {stats.total.num_failures}")
    if stats.total.num_requests > 0:
        fail_pct = 100 * stats.total.num_failures / stats.total.num_requests
        print(f"Failure rate   : {fail_pct:.1f}%")
    print(f"Median response: {stats.total.median_response_time} ms")
    print(f"95th percentile: {stats.total.get_response_time_percentile(0.95):.0f} ms")
    print(f"99th percentile: {stats.total.get_response_time_percentile(0.99):.0f} ms")
