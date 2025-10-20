import os

from typing import Any, Dict


def load_env_file(file_path: str = ".env"):
    """Load environment variables from .env file."""
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value


def set_env_vars_from_args(args, keys):
    """Set environment variables from argparse arguments."""
    for key in keys:
        value = getattr(args, key.lower(), None)
        if value is not None:
            os.environ[key.upper()] = str(value)


def get_smtp_config() -> Dict[str, Any]:
    """Get SMTP configuration from environment variables."""
    return {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT", 25)),
        "username": os.environ.get("SMTP_USERNAME"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "security": os.environ.get("SMTP_SECURITY", "none").lower(),
        "allow_insecure_tls": os.environ.get("ALLOW_INSECURE_TLS", "false").lower() == "true",
        "timeout": int(os.environ.get("TIMEOUT", 30)),
    }


def get_mail_config() -> Dict[str, Any]:
    """Get mail (IMAP/POP3) configuration from environment variables."""
    return {
        "protocol": os.environ.get("MAIL_PROTOCOL", "imap").lower(),
        "host": os.environ.get("MAIL_HOST"),
        "port": int(os.environ.get("MAIL_PORT", 993)),
        "username": os.environ.get("MAIL_USERNAME"),
        "password": os.environ.get("MAIL_PASSWORD"),
        "security": os.environ.get("MAIL_SECURITY", "ssl").lower(),
        "allow_insecure_tls": os.environ.get("ALLOW_INSECURE_TLS", "false").lower() == "true",
        "timeout": int(os.environ.get("TIMEOUT", 30)),
    }
