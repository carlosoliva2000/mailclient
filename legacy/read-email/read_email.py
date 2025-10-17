import poplib
import imaplib
import email
import re
import os
import sys
import argparse
import time
import logging
import json
from typing import List
import requests
import webbrowser
import base64
import ssl
import subprocess
import socket

from logging.handlers import RotatingFileHandler
from email import message_from_bytes
from email.header import decode_header


# Logging setup


LOG_PATH = os.path.join(os.path.expanduser("~"), ".config", "read-email")
os.makedirs(LOG_PATH, exist_ok=True)

format_str = "%(asctime)s [PID %(process)d] - %(funcName)s - %(levelname)s - %(message)s"
class LevelBasedFormatter(logging.Formatter):
    """Custom formatter to change format based on log level."""
    def format(self, record):
        if record.levelno == logging.INFO:
            fmt = "%(message)s"
        else:
            fmt = "%(levelname)s - %(message)s"
        formatter = logging.Formatter(fmt)
        return formatter.format(record)

formatter = logging.Formatter(format_str)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
logger.addHandler(console_handler)

file_handler = RotatingFileHandler(
    os.path.join(os.path.expanduser(LOG_PATH), 'read-email.log'),
    maxBytes=1024*1024, 
    backupCount=3
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def set_env_vars(args: argparse.Namespace) -> None:
    """
    Set environment variables from command-line arguments.

    Args:
        args (argparse.Namespace): Parsed command-line arguments.
    """
    env_vars = [
        "MAIL_PROTOCOL",
        "MAIL_HOST",
        "MAIL_PORT",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_SECURITY",
        "ALLOW_INSECURE_TLS",
        "TIMEOUT"
    ]
    for var in env_vars:
        value = getattr(args, var.lower(), None)
        if value is not None:
            os.environ[var] = str(value)


def load_env_file(file_path='.env'):
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            for line in file:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

load_env_file()


def connect_to_mailserver(use_mailhog=False):
    if use_mailhog:
        return "mailhog", "mailhog"

    protocol = os.environ.get('MAIL_PROTOCOL', 'imap').lower()
    host = os.environ.get('MAIL_HOST', 'localhost')
    port = int(os.environ.get('MAIL_PORT', '993'))
    email_address = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    security = os.environ.get('MAIL_SECURITY', 'ssl').lower()  # none | ssl | starttls
    allow_insecure_tls = os.environ.get('ALLOW_INSECURE_TLS', 'false').lower() == 'true'
    timeout = int(os.environ.get('TIMEOUT', 30))

    prev_timeout = socket.getdefaulttimeout()
    logger.debug(f"Previous default socket timeout: {prev_timeout}")
    socket.setdefaulttimeout(timeout)

    if not email_address or not password:
        logger.error("EMAIL_ADDRESS and EMAIL_PASSWORD environment variables must be set")
        raise ValueError("EMAIL_ADDRESS and EMAIL_PASSWORD environment variables must be set")

    logger.info(f"Connecting to {protocol.upper()} server {host}:{port} with {security.upper()} security")

    try:
        context = ssl.create_default_context()
        if allow_insecure_tls:
            logger.warning("Insecure TLS connections allowed (self-signed/unverified certificates).")
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        if protocol == 'pop3':
            if security == 'ssl':
                mail = poplib.POP3_SSL(host, port, timeout=timeout)
            else:
                mail = poplib.POP3(host, port, timeout=timeout)
                if security == 'starttls':
                    mail.stls(context=context)

            mail.user(email_address)
            mail.pass_(password)

        elif protocol == 'imap':
            if security == 'ssl':
                logger.info("Using implicit SSL (IMAP4_SSL)")
                mail = imaplib.IMAP4_SSL(host, port, ssl_context=context)
            else:
                logger.info("Using plain IMAP connection")
                mail = imaplib.IMAP4(host, port)
                if security == 'starttls':
                    logger.info("Starting STARTTLS session")
                    mail.starttls(ssl_context=context)

            logger.info("Logging in...")
            mail.login(email_address, password)
            logger.info("Selecting INBOX...")
            mail.select('INBOX')

        else:
            logger.error(f"Unsupported protocol: {protocol}")
            raise ValueError(f"Unsupported protocol: {protocol}")

        logger.info(f"Connected to mail server successfully using {protocol.upper()} ({security.upper()})")
        return mail, protocol

    except Exception as e:
        logger.error(f"Error connecting to mail server: {e}", exc_info=True)
        return None, None


def fetch_emails(mail, protocol):
    if protocol == "api":
        try:
            response = requests.get("http://localhost:8025/api/v2/messages")
            if response.status_code == 200:
                messages = response.json()
                logger.info(f"Found {messages['count']} messages using MailHog API")
                logger.debug(f"Raw MailHog API response: {json.dumps(messages, indent=2)}")
                return messages['items']
            else:
                logger.error(f"Error fetching emails from MailHog API: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching emails from MailHog API: {e}")
            return []
    else:
        try:
            if protocol == 'pop3':
                num_messages = len(mail.list()[1])
                logger.info(f"Found {num_messages} messages using POP3")
                return range(num_messages)
            elif protocol == 'imap':
                _, message_numbers = mail.search(None, 'UNSEEN')  # _, message_numbers = mail.search(None, 'ALL')
                num_messages = len(message_numbers[0].split())
                logger.info(f"Found {num_messages} messages using IMAP")
                return message_numbers[0].split()
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []


def decode_mime_words(value):
    """Decodifica encabezados MIME (p.ej. =?utf-8?q?...?=)"""
    if not value:
        return ""
    decoded_parts = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(enc or 'utf-8', errors='ignore'))
        else:
            decoded_parts.append(part)
    return ''.join(decoded_parts)


def list_mailboxes(mail):
    """Parse IMAP LIST response to a structured format."""
    status, folders = mail.list()
    if status != 'OK':
        logger.error("Failed to list mailboxes")
        return []
    
    parsed = []
    for f in folders:
        line = f.decode()

        # Get flags, delimiter, and name
        parts = line.split(' ')
        flags = parts[0].strip('()')
        delimiter = parts[-2].strip('"')
        name = parts[-1].strip('"')
        parsed.append({
            "flags": flags.split('\\')[1:],  # Split flags and remove leading backslash
            "delimiter": delimiter,
            "name": name
        })
    return parsed


def process_email(mail, email_data, protocol, download_dir, action_type, action_pattern, execute_path=None, pop3_delete=False):
    try:
        if protocol == "mailhog":
            logger.debug(f"Processing MailHog email: {json.dumps(email_data, indent=2)}")

            subject = email_data['Content']['Headers'].get('Subject', ['No Subject'])[0]
            from_data = email_data['From']
            sender = f"{from_data['Mailbox']}@{from_data['Domain']}"
            body = email_data['Content']['Body']

            logger.info(f"Processing MailHog email from {sender} with subject: {subject}")
            process_content(body, email_data, download_dir, action_type, action_pattern, subject, execute_path)
            return
        
        if protocol == 'pop3':
            logger.info(f"Fetching POP3 message ID {email_data + 1}")

            # Download the email
            status, lines, octets = mail.retr(email_data + 1)
            if status.startswith(b'+OK'):
                raw_email = b"\n".join(lines)
            else:
                logger.error(f"Failed to retrieve POP3 email ID {email_data + 1}")
                return
        elif protocol == 'imap':
            logger.info(f"Fetching IMAP message ID {email_data.decode()}")

            # Download the email
            status, msg_data = mail.fetch(email_data, '(RFC822)')
            if status != 'OK':
                logger.error(f"Failed to fetch IMAP email ID {email_data.decode()}")
                return
            raw_email = msg_data[0][1]
        else:
            logger.error(f"Unsupported protocol: {protocol}")
            return

        # Decode email
        msg = message_from_bytes(raw_email)

        # Get metadata
        subject = decode_mime_words(msg.get("Subject"))
        sender = email.utils.parseaddr(msg.get("From"))[1]
        logger.info(f"Processing email from {sender} with subject: {subject}")

        # Walk through email parts
        if msg.is_multipart():
            logger.info("Processing multipart email...")
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = part.get_content_disposition()
                
                # HTML or plain text parts
                if content_type in ("text/plain", "text/html") and disposition != "attachment":
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                    process_content(body, msg, download_dir, action_type, action_pattern, subject, execute_path)

                # 3.Attachments
                elif disposition == "attachment":
                    filename = part.get_filename()
                    if filename:
                        filepath = os.path.join(download_dir, filename)
                        with open(filepath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        logger.info(f"Saved attachment: {filepath}")
        else:
            logger.info("Processing non-multipart email...")
            body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
            process_content(body, msg, download_dir, action_type, action_pattern, subject, execute_path)

        if protocol == 'pop3' and pop3_delete:
            try:
                mail.dele(email_data + 1)
                logger.info(f"Deleted POP3 message ID {email_data + 1} after processing.")
            except Exception as e:
                logger.error(f"Failed to delete POP3 message ID {email_data + 1}: {e}")
    except Exception as e:
        logger.error(f"Error processing email ID {email_data.decode()}: {e}", exc_info=True)


def process_content(body, email_message, download_dir, action_type, action_pattern, subject, execute_path=None):
    if action_pattern and (re.search(action_pattern, body, re.IGNORECASE) or re.search(action_pattern, subject, re.IGNORECASE)):
        logger.info(f"Action pattern '{action_pattern}' found in email. Performing {action_type} action.")
        
        if action_type == 'download':
            download_attachment(email_message, download_dir)
        elif action_type == 'navigate':
            click_link(body)
        elif action_type == 'execute':
            if execute_path:
                download_and_execute(email_message, download_dir, execute_path)
            else:
                logger.error("Execute path not provided for execute action type")
    else:
        logger.info(f"No action pattern found or actions not enabled. Skipping {action_type} action.")


def download_attachment(email_message, download_dir):
    if isinstance(email_message, dict):  # MailHog email
        for attachment in email_message.get('MIME', {}).get('Parts', []):
            if 'FileName' in attachment.get('Headers', {}):
                filename = attachment['Headers']['FileName'][0]
                content = base64.b64decode(attachment['Body'])
                filepath = os.path.join(download_dir, filename)
                try:
                    with open(filepath, 'wb') as f:
                        f.write(content)
                    logger.info(f"Attachment downloaded: {filepath}")
                except Exception as e:
                    logger.error(f"Error downloading attachment: {e}")
    else:  # Regular email
        for part in email_message.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue

            filename = part.get_filename()
            if filename:
                filepath = os.path.join(download_dir, filename)
                try:
                    with open(filepath, 'wb') as f:
                        f.write(part.get_payload(decode=True))
                    logger.info(f"Attachment downloaded: {filepath}")
                except Exception as e:
                    logger.error(f"Error downloading attachment: {e}")


def click_link(body):
    logger.info("Searching for links in email body...")
    # print(f"Email body: {body}")
    # match = re.search(r'(https?://\S+)', body)
    match = re.search(r'https?://[^\s"<>]+', body)
    if match:
        link = match.group(0)
        logger.info(f"Opening link: {link}")
        try:
            webbrowser.open(link)
            logger.info(f"Link opened successfully in default browser")
        except Exception as e:
            logger.error(f"Error opening link: {e}")


def download_and_execute(email_message, download_dir, execute_path):
    download_attachment(email_message, download_dir)
    for filename in os.listdir(download_dir):
        filepath = os.path.join(download_dir, filename)
        if os.path.isfile(filepath):
            try:
                dest_path = os.path.join(execute_path, filename)
                os.makedirs(execute_path, exist_ok=True)
                os.rename(filepath, dest_path)
                logger.info(f"Moved file to execution path: {dest_path}")
                if not os.access(dest_path, os.X_OK):
                    logger.info(f"Setting execute permissions for: {dest_path}")
                    os.chmod(dest_path, 0o755)

                if os.access(dest_path, os.X_OK):
                    subprocess.run([dest_path], check=True)
                    logger.info(f"Executed file: {dest_path}")
            except Exception as e:
                logger.error(f"Error executing file {filepath}: {e}")


def main(run_forever=False, custom_download_dir=None, use_mailhog=False, action_type='download', 
         action_pattern=None, execute_path=None, pop3_delete=False):
    download_dir = custom_download_dir or os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    while True:
        mail, protocol = connect_to_mailserver(use_mailhog)
        if not mail and protocol != "api":
            if not run_forever:
                sys.exit(1)
            logger.warning("Failed to connect to mail server. Retrying in 60 seconds...")
            time.sleep(60)
            continue
        
        logger.info("Checking for new emails...")
        new_emails = fetch_emails(mail, protocol)
        
        if not new_emails:
            logger.info("No new emails found.")
        else:
            for email_data in new_emails:
                process_email(mail, email_data, protocol, download_dir, action_type, 
                            action_pattern, execute_path, pop3_delete)
        
        if protocol == 'pop3':
            mail.quit()
        elif protocol == 'imap':
            mail.close()
            mail.logout()
        
        if not run_forever:
            break
        
        logger.info("Waiting 60 seconds before checking again...")
        time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read emails from a mail server.")

    parser.add_argument(
        "--mail-host", "-H", help="IMAP/POP3 host", required=True
    )
    parser.add_argument(
        "--mail-port",
        "-P",
        type=int,
        help="IMAP/POP3 port",
        required=True,
    )
    parser.add_argument(
        "--mail-protocol",
        "-r",
        choices=["imap", "pop3"],
        help="Mail protocol to use: imap or pop3. Default is imap",
        default="imap"
    )
    parser.add_argument(
        "--mail-username",
        "-u",
        help="IMAP/POP3 username (email address). Not required if no authentication is needed.",
        default=None
    )
    parser.add_argument(
        "--mail-password", 
        "-p",
        help="IMAP/POP3 password. Not required if no authentication is needed.",
        default=None
    )
    parser.add_argument(
        "--mail-security",
        "-S",
        choices=["none", "starttls", "ssl"],
        help="Type of IMAP/POP3 connection: none, starttls, ssl",
        default="none"
    )
    parser.add_argument(
        "--allow-insecure-tls",
        "-I",
        action="store_true",
        help="Allow unverified/self-signed TLS certificates",
        default=False,
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        help="IMAP/POP3 connection timeout in seconds (default: 30)",
        default=30
    )
    parser.add_argument(
        "--pop3-delete",
        action="store_true",
        help="Delete POP3 emails after processing",
        default=False
    )


    parser.add_argument("--run-forever", action="store_true", help="Run continuously, checking for emails at intervals", default=False)
    parser.add_argument("--interval", type=int, default=60, help="Interval in seconds between email checks")
    parser.add_argument("--action-type", choices=['download', 'navigate', 'execute'], 
                       default='download', help="Type of action to perform")
    parser.add_argument("--action-pattern", help="Regex pattern to match in email body or subject")
    parser.add_argument("--download-dir", help="Custom download directory for attachments")
    parser.add_argument("--execute-path", help="Path where to move and execute downloaded files")
    parser.add_argument("--use-mailpit", action="store_true", help="Use MailPit for testing")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args, unknown = parser.parse_known_args()

    if args.debug:
        console_handler.setFormatter(formatter)
    else:
        console_handler.setFormatter(LevelBasedFormatter())
        console_handler.setLevel(logging.INFO)

    logger.info("Starting read-email.")
    if unknown:
        logger.warning(f"Unknown arguments ignored: {unknown}")

    # Set environment variables from command-line arguments
    set_env_vars(args)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    main(run_forever=args.run_forever,
         custom_download_dir=args.download_dir, 
         use_mailhog=args.use_mailpit,
         action_type=args.action_type, 
         action_pattern=args.action_pattern,
         execute_path=args.execute_path,
         pop3_delete=args.pop3_delete)
    
    logger.info("Finishing read-email.")
