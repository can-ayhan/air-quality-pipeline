import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

import alerts


def context(**ti):
    fields = {"task_id": "dbt_build", "dag_id": "air_quality_daily", "try_number": 1,
              "run_id": "scheduled__2026-07-02T06:00:00+00:00", **ti}
    return {"ti": SimpleNamespace(**fields), "exception": RuntimeError("Bash command failed")}


@pytest.fixture
def webhook():
    """A local HTTP server that keeps what is posted to it."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/hook", received
    server.shutdown()


def test_message_names_the_task_the_run_and_the_error():
    text = alerts.failure_message(context(log_url="http://localhost:8080/dags/air_quality_daily/runs/x"))
    assert "dbt_build failed" in text
    assert "run scheduled__2026-07-02T06:00:00+00:00, attempt 1" in text
    assert "RuntimeError: Bash command failed" in text
    assert text.endswith("Log: http://localhost:8080/dags/air_quality_daily/runs/x")


def test_alert_is_posted_as_json_text(webhook, monkeypatch):
    url, received = webhook
    monkeypatch.setenv("ALERT_WEBHOOK_URL", url)
    alerts.notify_failure(context())
    assert len(received) == 1
    assert received[0]["text"].startswith("Air quality pipeline: dbt_build failed")


def test_without_a_webhook_the_alert_goes_to_the_log(monkeypatch, caplog):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    alerts.notify_failure(context())
    assert "alert not sent" in caplog.text and "dbt_build failed" in caplog.text


def test_an_unreachable_webhook_does_not_raise(monkeypatch, caplog):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://127.0.0.1:9/hook")
    alerts.notify_failure(context())
    assert "alert not sent" in caplog.text
