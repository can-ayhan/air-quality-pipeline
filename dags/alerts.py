"""Failure alerts for the DAGs.

One message per failed task, sent once its retries are used up, to a chat
webhook that accepts {"text": ...} (Slack, Mattermost, Google Chat and others).
Without ALERT_WEBHOOK_URL the message only goes to the task log.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

log = logging.getLogger(__name__)


def failure_message(context) -> str:
    ti = context["ti"]
    lines = [
        f"Air quality pipeline: {ti.task_id} failed",
        f"DAG {ti.dag_id}, run {ti.run_id}, attempt {ti.try_number}",
    ]
    exception = context.get("exception")
    if exception:
        lines.append(f"{type(exception).__name__}: {exception}"[:500])
    log_url = getattr(ti, "log_url", None)
    if log_url:
        lines.append(f"Log: {log_url}")
    return "\n".join(lines)


def notify_failure(context) -> None:
    """Task on_failure_callback."""
    text = failure_message(context)
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        log.warning("ALERT_WEBHOOK_URL is not set, alert not sent:\n%s", text)
        return
    request = urllib.request.Request(
        url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            log.info("alert sent (HTTP %s)", response.status)
    except OSError as exc:
        # an alert that cannot be delivered must not replace the failure it is about
        log.error("alert not sent (%s):\n%s", exc, text)
