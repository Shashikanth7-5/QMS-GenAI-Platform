import os
import smtplib
from email.message import EmailMessage

from services.agents.audit import log_agent_event


def _send_email(recipient: str, subject: str, message: str, from_default: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    if not smtp_host or not recipient:
        return False

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = os.getenv("SMTP_FROM", from_default)
    email["To"] = recipient
    email.set_content(message)

    with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "25")), timeout=10) as client:
        if os.getenv("SMTP_STARTTLS", "false").lower() == "true":
            client.starttls()
        username = os.getenv("SMTP_USERNAME", "")
        if username:
            client.login(username, os.getenv("SMTP_PASSWORD", ""))
        client.send_message(email)
    return True


def send_agent_alert(subject: str, message: str, *, run_id: str, details: dict = None) -> bool:
    """Always creates an app alert; sends email when SMTP is configured."""
    recipient = os.getenv("AGENT_ALERT_EMAIL", "").strip()
    event = log_agent_event(
        "responsible_ai_supervisor",
        "alert",
        "alert",
        run_id=run_id,
        details={"subject": subject, "message": message, **(details or {})},
    )
    if not os.getenv("SMTP_HOST", "").strip() or not recipient:
        event["emailSent"] = False
        return False

    try:
        return _send_email(recipient, subject, message, "qms-agents@localhost")
    except Exception as exc:
        log_agent_event(
            "responsible_ai_supervisor",
            "email_alert_failed",
            "error",
            run_id=run_id,
            details={"error": str(exc)},
        )
        return False


def send_email_notification(
    recipient: str,
    subject: str,
    message: str,
    *,
    run_id: str,
    agent_name: str = "workflow_notification_agent",
    details: dict = None,
) -> bool:
    """Log every workflow notification; send email when SMTP and recipient are available."""
    recipient = (recipient or "").strip()
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    event = log_agent_event(
        agent_name,
        "email_notification",
        "done" if smtp_host and recipient else "skipped",
        run_id=run_id,
        details={
            "recipient": recipient,
            "subject": subject,
            "message": message,
            "emailConfigured": bool(smtp_host),
            **(details or {}),
        },
    )
    if not smtp_host or not recipient:
        event["emailSent"] = False
        return False

    try:
        return _send_email(recipient, subject, message, "qms-workflow@localhost")
    except Exception as exc:
        log_agent_event(
            agent_name,
            "email_notification_failed",
            "error",
            run_id=run_id,
            details={"recipient": recipient, "subject": subject, "error": str(exc)},
        )
        return False
