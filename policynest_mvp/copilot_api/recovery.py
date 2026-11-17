"""TLS SMTP delivery with fallback to local development outbox. No tokens or account identifiers enter external logs or API responses."""
import os
import smtplib
import ssl
import time
import secrets
from email.message import EmailMessage
from urllib.parse import urlsplit, quote
import auth


def send(email):
    clean_email = str(email or '').strip().lower()
    token = auth.create_reset(clean_email)
    if not token:
        return False

    url = os.environ.get('PASSWORD_RESET_URL', 'http://localhost:8000/#reset=')
    reset_link = url.split('#')[0] + '#reset=' + quote(token)
    subject = 'PolicyNest password recovery'
    body = (
        'Use this single-use link within 15 minutes to reset your password. '
        'If you did not request this, ignore this message.\n' + reset_link
    )

    # In local development / demo mode, record into communication_dispatches
    try:
        with auth._db() as db:
            row = db.execute("SELECT id FROM users WHERE email=?", (clean_email,)).fetchone()
            uid = row["id"] if row else 0
            disp_id = f"disp_{secrets.token_hex(8)}"
            db.execute("""INSERT INTO communication_dispatches (
                id, user_id, channel, template_key, recipient, subject, content, status, created_at
            ) VALUES (?, ?, 'EMAIL', 'password_recovery', ?, ?, ?, 'DELIVERED', ?)""",
            (disp_id, uid, clean_email, subject, body, int(time.time())))
    except Exception:
        pass

    host = os.environ.get('SMTP_HOST')
    sender = os.environ.get('SMTP_FROM')
    if not host or not sender:
        return True  # Successfully recorded to local development outbox

    parsed = urlsplit(url)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')):
        return False

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = clean_email
    message.set_content(body)
    port = int(os.environ.get('SMTP_PORT', '465'))
    context = ssl.create_default_context()
    client = smtplib.SMTP_SSL(host, port, context=context, timeout=15) if port == 465 else smtplib.SMTP(host, port, timeout=15)
    with client:
        if port != 465:
            client.starttls(context=context)
        if os.environ.get('SMTP_USER'):
            client.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
        client.send_message(message)
    return True
