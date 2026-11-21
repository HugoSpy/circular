"""Email verification delivery; development links stay on the local console."""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from backend.app.core.config import email_config, verification_url

logger = logging.getLogger("circular.security")


def send_verification(email: str, token: str) -> None:
    config = email_config()
    link = verification_url(token)
    if not config["host"]:
        logger.info("email_verification_link=%s", link)
        return

    message = EmailMessage()
    message["Subject"] = "Confirmez votre adresse pour Circular"
    message["From"] = config["sender"]
    message["To"] = email
    message.set_content(
        "Pour confirmer votre adresse et activer votre compte Circular, ouvrez ce lien :\n\n"
        f"{link}\n\nCe lien expire dans 30 minutes. Si vous n’êtes pas à l’origine de cette demande, ignorez ce message.\n"
    )
    with smtplib.SMTP(str(config["host"]), int(config["port"]), timeout=10) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        if config["username"]:
            server.login(str(config["username"]), str(config["password"]))
        server.send_message(message)
