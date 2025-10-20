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


def get_smtp_config(include_imap: bool = False) -> Dict[str, Any]:
    """Get SMTP configuration from environment variables."""
    config = {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT", 25)),
        "username": os.environ.get("SMTP_USERNAME"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "security": os.environ.get("SMTP_SECURITY", "none").lower(),
        "allow_insecure_tls": os.environ.get("ALLOW_INSECURE_TLS", "false").lower() == "true",
        "timeout": int(os.environ.get("TIMEOUT", 30)),
    }

    if include_imap:
        config["imap_config"] = get_mail_config()

        if config["imap_config"]["host"] is None:
            config["imap_config"]["host"] = config["host"]  # Use SMTP host as default IMAP host
        if config["imap_config"]["username"] is None:
            config["imap_config"]["username"] = config["username"]  # Use SMTP username as default IMAP username
        if config["imap_config"]["password"] is None:
            config["imap_config"]["password"] = config["password"]  # Use SMTP password as default IMAP password
        if config["security"] != config["imap_config"]["security"]:
            config["imap_config"]["security"] = config["security"]  # Use SMTP security as default IMAP security
        
        # Set specific Sent folder
        config["imap_config"]["folder"] = os.environ.get("MAIL_FOLDER", "Sent")

        # Ensure protocol is IMAP for saving sent emails
        config["imap_config"]["protocol"] = "imap"
    
    return config


def get_mail_config() -> Dict[str, Any]:
    """Get mail (IMAP/POP3) configuration from environment variables."""
    return {
        "protocol": os.environ.get("MAIL_PROTOCOL", "imap").lower(),
        "host": os.environ.get("MAIL_HOST"),
        "port": int(os.environ.get("MAIL_PORT", 993)),
        "username": os.environ.get("MAIL_USERNAME"),
        "password": os.environ.get("MAIL_PASSWORD"),
        "security": os.environ.get("MAIL_SECURITY", "none").lower(),
        "allow_insecure_tls": os.environ.get("ALLOW_INSECURE_TLS", "false").lower() == "true",
        "timeout": int(os.environ.get("TIMEOUT", 30)),
    }
