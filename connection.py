import ssl
import smtplib
import imaplib
import poplib
import socket

from typing import Any, Dict, Tuple, Union
from log import get_logger
# from mailclient.log import get_logger


logger = get_logger()


def create_ssl_context(allow_insecure: bool = False) -> ssl.SSLContext:
    """Create an SSL context, optionally allowing insecure/self-signed certificates."""
    context = ssl.create_default_context()
    if allow_insecure:
        logger.warning("Allowing insecure/self-signed TLS connections.")
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def connect_smtp(config: Dict[str, Any]) -> smtplib.SMTP:
    """Return a connected SMTP client."""
    context = create_ssl_context(config["allow_insecure_tls"])
    if config["security"] == "ssl":
        server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=config["timeout"], context=context)
    else:
        server = smtplib.SMTP(config["host"], config["port"], timeout=config["timeout"])
        if config["security"] == "starttls":
            server.starttls(context=context)

    if config["username"] and config["password"]:
        server.login(config["username"], config["password"])
    logger.info(f"Connected to SMTP {config['host']}:{config['port']} ({config['security']})")
    return server


def connect_mail(config: Dict[str, Any]) -> Tuple[ Union[imaplib.IMAP4, imaplib.IMAP4_SSL, poplib.POP3, poplib.POP3_SSL], str]:
    """Return a connected IMAP/POP3 client."""
    socket.setdefaulttimeout(config["timeout"])
    context = create_ssl_context(config["allow_insecure_tls"])

    if config["protocol"] == "imap":
        if config["security"] == "ssl":
            mail = imaplib.IMAP4_SSL(config["host"], config["port"], ssl_context=context)
        else:
            mail = imaplib.IMAP4(config["host"], config["port"])
            if config["security"] == "starttls":
                mail.starttls(ssl_context=context)
        mail.login(config["username"], config["password"])
        mail.select("INBOX")
        logger.info(f"Connected to IMAP {config['host']}:{config['port']}")
        return mail, "imap"

    elif config["protocol"] == "pop3":
        if config["security"] == "ssl":
            mail = poplib.POP3_SSL(config["host"], config["port"], timeout=config["timeout"])
        else:
            mail = poplib.POP3(config["host"], config["port"], timeout=config["timeout"])
            if config["security"] == "starttls":
                mail.stls(context=context)
        mail.user(config["username"])
        mail.pass_(config["password"])
        logger.info(f"Connected to POP3 {config['host']}:{config['port']}")
        return mail, "pop3"

    else:
        raise ValueError(f"Unsupported protocol: {config['protocol']}")
