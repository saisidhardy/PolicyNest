"""Optional TLS SMTP delivery. No tokens or account identifiers enter logs or API responses."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit,quote
import auth


def send(email):
    host=os.environ.get('SMTP_HOST');sender=os.environ.get('SMTP_FROM');url=os.environ.get('PASSWORD_RESET_URL')
    if not host or not sender or not url:return False
    parsed=urlsplit(url)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):return False
    token=auth.create_reset(email)
    if not token:return False
    message=EmailMessage();message['Subject']='PolicyNest password recovery';message['From']=sender;message['To']=str(email).strip()
    message.set_content('Use this single-use link within 15 minutes to reset your password. If you did not request this, ignore this message.\n'+url.split('#')[0]+'#reset='+quote(token))
    port=int(os.environ.get('SMTP_PORT','465'));context=ssl.create_default_context()
    client=smtplib.SMTP_SSL(host,port,context=context,timeout=15) if port==465 else smtplib.SMTP(host,port,timeout=15)
    with client:
        if port!=465:client.starttls(context=context)
        if os.environ.get('SMTP_USER'):client.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
        client.send_message(message)
    return True
