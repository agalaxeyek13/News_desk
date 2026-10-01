"""
Sends the composed briefing email.

Two methods, picked by FDE_MAIL_METHOD in .env:
  - "outlook" (default): drives the desktop Outlook app via COM automation
    (pywin32). Uses whatever account Outlook on this machine is already
    signed into — no SMTP credentials, no app password, no IT ticket.
    Requires Outlook desktop installed and signed in on this machine.
    Outlook may show a one-time "a program is sending mail on your behalf"
    security prompt the first time.
  - "smtp": plain smtplib against FDE_SMTP_* — for a server deployment
    with no Outlook desktop, once IT has enabled SMTP AUTH (or this is
    swapped for Microsoft Graph's sendMail) for the sending mailbox.
"""

import logging
import os

from config import FDE_SMTP_HOST, FDE_SMTP_PORT, FDE_SMTP_USER, FDE_SMTP_PASSWORD, FDE_SENDER, FDE_RECIPIENTS

logger = logging.getLogger(__name__)

FDE_MAIL_METHOD = os.getenv("FDE_MAIL_METHOD", "outlook").strip().lower()


def _send_via_outlook(subject: str, html_body: str) -> bool:
    """Compose and send through the desktop Outlook app already signed in on this machine."""
    try:
        import win32com.client  # noqa: PLC0415
    except ImportError:
        logger.error("FDE mailer: pywin32 not installed (`pip install pywin32`) — required for FDE_MAIL_METHOD=outlook")
        return False

    if not FDE_RECIPIENTS:
        logger.error("FDE mailer: no recipients configured (FDE_RECIPIENTS is empty)")
        return False

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # olMailItem
        mail.Subject = subject
        mail.HTMLBody = html_body
        mail.To = "; ".join(FDE_RECIPIENTS)
        if FDE_SENDER:
            # Send from a shared/secondary mailbox already added to this Outlook profile.
            mail.SentOnBehalfOfName = FDE_SENDER
        mail.Send()
        logger.info("FDE Briefing sent via Outlook to %d recipient(s)", len(FDE_RECIPIENTS))
        return True
    except Exception as e:
        logger.error("FDE mailer (Outlook COM) error: %s", e)
        return False


def _send_via_smtp(subject: str, html_body: str) -> bool:
    """Plain SMTP send — needs SMTP AUTH enabled by IT for the sending mailbox."""
    import smtplib  # noqa: PLC0415
    from email.mime.multipart import MIMEMultipart  # noqa: PLC0415
    from email.mime.text import MIMEText  # noqa: PLC0415

    if not FDE_RECIPIENTS:
        logger.error("FDE mailer: no recipients configured (FDE_RECIPIENTS is empty)")
        return False
    if not FDE_SMTP_USER or not FDE_SMTP_PASSWORD:
        logger.error("FDE mailer: SMTP credentials not configured (FDE_SMTP_USER/FDE_SMTP_PASSWORD)")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = FDE_SENDER or FDE_SMTP_USER
    msg["To"] = ", ".join(FDE_RECIPIENTS)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(FDE_SMTP_HOST, FDE_SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(FDE_SMTP_USER, FDE_SMTP_PASSWORD)
            server.sendmail(msg["From"], FDE_RECIPIENTS, msg.as_string())
        logger.info("FDE Briefing sent via SMTP to %d recipient(s)", len(FDE_RECIPIENTS))
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error("FDE mailer auth failed: %s", e)
    except smtplib.SMTPException as e:
        logger.error("FDE mailer SMTP error: %s", e)
    except Exception as e:
        logger.error("FDE mailer unexpected error: %s", e)
    return False


def send_briefing(subject: str, html_body: str) -> bool:
    """Send the briefing email via the configured method. Returns True on success."""
    if FDE_MAIL_METHOD == "smtp":
        return _send_via_smtp(subject, html_body)
    return _send_via_outlook(subject, html_body)
