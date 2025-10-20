import argparse
import base64
import email
import imaplib
import json
import os
import poplib
import subprocess
import sys
import time
import re
import requests
import webbrowser

from typing import Any, Dict, List, Optional, Union

from email import message_from_bytes
from log import get_logger
from config import get_mail_config, set_env_vars_from_args
from connection import connect_mail
from mail_utils import decode_mime_words


logger = get_logger()


def register_arguments(parser: argparse.ArgumentParser):
    """Register command-line arguments for the read command."""
    parser.add_argument("--mail-host", "-H", required=True, help="Mail server host.")
    parser.add_argument("--mail-port", "-P", type=int, required=True, help="Mail server port.")
    parser.add_argument("--mail-protocol", "-r", choices=["imap", "pop3", "mailpit"], default="imap", help="Mail protocol to use: imap, pop3, mailpit (default: imap). Mailpit is for local testing servers like MailPit.")
    parser.add_argument("--mail-username", "-u", default=None, help="Mail server username. Not required if no authentication is needed.")
    parser.add_argument("--mail-password", "-p", default=None, help="Mail server password. Not required if no authentication is needed.")
    parser.add_argument("--mail-security", "-S", choices=["none", "starttls", "ssl"], default="none", help="Type of IMAP/POP3 connection: none, starttls, or ssl (default: none).")
    parser.add_argument("--allow-insecure-tls", "-I", action="store_true", default=False, help="Allow unverified/self-signed TLS certificates")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Connection timeout in seconds (default: 30).")
    parser.add_argument("--pop3-delete", action="store_true", default=False, help="Delete emails from server after downloading (POP3 only).")
    parser.add_argument("--run-forever", action="store_true", default=False, help="Run continuously, checking for emails at intervals.")
    parser.add_argument("--interval", type=int, default=60, help="Interval in seconds between email checks when running continuously (default: 60).")
    parser.add_argument("--action-type", choices=["none", "download", "navigate", "execute"], default="none", help="Action to perform on matched emails: none, download, navigate, execute (default: none).")
    parser.add_argument("--action-pattern", help="Regex pattern to match in subject or body")
    parser.add_argument("--download-dir", help="Directory for attachments")
    parser.add_argument("--execute-path", help="Directory to move and execute files")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debug logging.")


def read_email_cli(args: argparse.Namespace):
    """Read emails using CLI arguments."""

    # Set env vars from CLI args
    set_env_vars_from_args(args, [
        "MAIL_HOST", "MAIL_PORT", "MAIL_PROTOCOL", "MAIL_USERNAME",
        "MAIL_PASSWORD", "MAIL_SECURITY", "ALLOW_INSECURE_TLS", "TIMEOUT"
    ])

    mail_config = get_mail_config()

    read_email(
        mail_config=mail_config,
        run_forever=args.run_forever,
        interval=args.interval,
        action_type=args.action_type,
        action_pattern=args.action_pattern,
        download_dir=args.download_dir,
        execute_path=args.execute_path,
        pop3_delete=args.pop3_delete
    )


def fetch_emails(
    client: Union[imaplib.IMAP4, imaplib.IMAP4_SSL, poplib.POP3, poplib.POP3_SSL],
    protocol: str
):
    """Fetch email list from the server, depending on protocol."""
    if protocol == "api":
        try:
            response = requests.get("http://localhost:8025/api/v2/messages")
            if response.status_code == 200:
                messages = response.json()
                logger.info(f"Found {messages['count']} messages using MailPit API")
                logger.debug(f"Raw MailPit API response: {json.dumps(messages, indent=2)}")
                return messages['items']
            else:
                logger.error(f"Error fetching emails from MailPit API: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching emails from MailPit API: {e}")
            return []
    else:
        try:
            if protocol == 'pop3':
                num_messages = len(client.list()[1])
                logger.info(f"Found {num_messages} messages using POP3")
                return range(num_messages)
            elif protocol == 'imap':
                _, message_numbers = client.search(None, 'UNSEEN')  # _, message_numbers = mail.search(None, 'ALL')
                num_messages = len(message_numbers[0].split())
                logger.info(f"Found {num_messages} messages using IMAP")
                return message_numbers[0].split()
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []


def list_mailboxes(client: Union[imaplib.IMAP4, imaplib.IMAP4_SSL]) -> List[Dict[str, str]]:
    """Parse IMAP LIST response to a structured format."""
    status, folders = client.list()
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


def download_attachment(email_message: Any, download_dir: str):
    """Download attachments from the email message to the specified directory."""
    if isinstance(email_message, dict):  # MailPit email
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


def click_link(body: str):
    """Find and open the first link in the email body."""
    logger.info("Searching for links in email body...")
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


def download_and_execute(email_message: Any, download_dir: str, execute_path: str):
    """Download attachments and execute them from the specified path."""
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


def process_content(
    subject: str,
    body: str,
    email_message: Any,
    download_dir: str,
    action_type: Optional[str],
    action_pattern: Optional[str],
    execute_path: Optional[str] = None
):
    """Process email content based on action type and pattern."""
    if action_type == 'none' or action_type is None or action_pattern is None:
        logger.info("No action specified or action pattern not provided. Skipping actions.")
        return
    logger.info(f"Action type: {action_type}, Action pattern: {action_pattern}")
    if re.search(action_pattern, body, re.IGNORECASE) or re.search(action_pattern, subject, re.IGNORECASE):
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
            logger.error(f"Unknown action type: {action_type}")


def process_email(
    client: Union[imaplib.IMAP4, imaplib.IMAP4_SSL, poplib.POP3, poplib.POP3_SSL],
    email_data: Any,
    protocol: str,
    download_dir: str,
    action_type: Optional[str] = None,
    action_pattern: Optional[str] = None,
    execute_path: Optional[str] = None,
    pop3_delete: bool = False
):
    """Process a single email: download, parse, and take actions."""
    try:
        if protocol == "mailpit":
            logger.debug(f"Processing MailPit email: {json.dumps(email_data, indent=2)}")

            subject = email_data['Content']['Headers'].get('Subject', ['No Subject'])[0]
            from_data = email_data['From']
            sender = f"{from_data['Mailbox']}@{from_data['Domain']}"
            body = email_data['Content']['Body']

            logger.info(f"Processing MailPit email from {sender} with subject: {subject}")
            process_content(subject, body, email_data, download_dir, action_type, action_pattern, execute_path)
            return
        
        if protocol == 'pop3':
            logger.info(f"Fetching POP3 message ID {email_data + 1}")

            # Download the email
            status, lines, octets = client.retr(email_data + 1)
            if status.startswith(b'+OK'):
                raw_email = b"\n".join(lines)
            else:
                logger.error(f"Failed to retrieve POP3 email ID {email_data + 1}")
                return
        elif protocol == 'imap':
            logger.info(f"Fetching IMAP message ID {email_data.decode()}")

            # Download the email
            status, msg_data = client.fetch(email_data, '(RFC822)')
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
                    process_content(subject, body, msg, download_dir, action_type, action_pattern, execute_path)

                # Attachments
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
            process_content(subject, body, msg, download_dir, action_type, action_pattern, execute_path)

        if protocol == 'pop3' and pop3_delete:
            try:
                client.dele(email_data + 1)
                logger.info(f"Deleted POP3 message ID {email_data + 1} after processing.")
            except Exception as e:
                logger.error(f"Failed to delete POP3 message ID {email_data + 1}: {e}")
    except Exception as e:
        logger.error(f"Error processing email ID {email_data.decode()}: {e}", exc_info=True)


def read_email(
    mail_config: Dict[str, Any],
    run_forever: bool = False,
    interval: int = 60,
    action_type: Optional[str] = None,
    action_pattern: Optional[str] = None,
    download_dir: Optional[str] = None,
    execute_path: Optional[str] = None,
    pop3_delete: bool = False
):
    """Read emails from the mail server and process them."""
    download_dir = download_dir or os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    while True:
        mail, protocol = connect_mail(mail_config)
        if not mail and protocol != "api":
            if not run_forever:
                sys.exit(1)
            logger.warning(f"Failed to connect to mail server. Retrying in {interval} seconds...")
            time.sleep(interval)
            continue
        
        logger.info("Checking for new emails...")
        new_emails = fetch_emails(mail, protocol)
        
        if not new_emails:
            logger.info("No new emails found.")
        else:
            for email_data in new_emails:
                process_email(mail, email_data, protocol, download_dir, action_type, action_pattern, execute_path, pop3_delete)
        
        if protocol == 'pop3':
            mail.quit()
        elif protocol == 'imap':
            mail.close()
            mail.logout()
        
        if not run_forever:
            break
        
        logger.info(f"Waiting {interval} seconds before checking again...")
        time.sleep(interval)
