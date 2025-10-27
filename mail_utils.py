import imaplib
import re
import time
import requests

from datetime import datetime
from typing import Dict, List, Optional, Union, Tuple
from email import message_from_bytes
from email.message import Message
from email.utils import parsedate_tz, mktime_tz
from email.header import decode_header

from log import get_logger


logger = get_logger()

def decode_mime_words(value: str) -> str:
    """Decode MIME encoded-words (e.g. =?utf-8?q?...?=)"""
    if not value:
        return ""
    
    decoded = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="ignore"))
        else:
            decoded.append(part)
    
    return "".join(decoded)


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


def save_to_sent_folder(
    imap_client: Union[imaplib.IMAP4, imaplib.IMAP4_SSL],
    sent_folder: str,
    msg_bytes: bytes
) -> bool:
    """Save the sent email to the specified Sent folder."""
    folders = list_mailboxes(imap_client)
    folder_names = [f["name"] for f in folders]
    if sent_folder not in folder_names:
        logger.warning(f"Sent folder '{sent_folder}' does not exist. Attempting to create it.")
        try:
            imap_client.create(sent_folder)
            logger.info(f"Created Sent folder: {sent_folder}")
        except Exception as e:
            logger.error(f"Failed to create Sent folder '{sent_folder}': {e}")
            return False
        
    try:
        # Try to get original date from the message for proper timestamping
        msg = message_from_bytes(msg_bytes)
        date_header = msg.get("Date")
        if date_header:
            time_tuple = parsedate_tz(date_header)
            timestamp = mktime_tz(time_tuple)
            internal_date = imaplib.Time2Internaldate(time.localtime(timestamp))
        else:
            internal_date = imaplib.Time2Internaldate(time.time())
    except Exception as e:
        logger.warning(f"Failed to parse Date header for internal date: {e}")
        internal_date = imaplib.Time2Internaldate(time.localtime())


    try:
        imap_client.append(sent_folder, '\\Seen', internal_date, msg_bytes)
        logger.info(f"Email saved to Sent folder: {sent_folder}")
        return True
    except Exception as e:
        logger.error(f"Failed to save email to Sent folder: {e}")
        return False


def parse_datetime_flexible(s: str) -> Optional[float]:
    """
    Parse a user-provided date/time string into a timestamp (seconds since epoch).
    Accepts:
      - YYYY-MM-DD
      - YYYY-MM-DDTHH:MM
      - YYYY-MM-DDTHH:MM:SS
      - YYYY-MM-DD HH:MM[:SS]
      - Full ISO variations (if Python can parse)
    Returns None if parsing fails.
    """
    if not s:
        return None
    s = s.strip()
    # Try fromisoformat (Python 3.7+)
    try:
        # Handle date-only -> set midnight
        if "T" in s or "-" in s and (":" in s):
            dt = datetime.fromisoformat(s)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            dt = datetime.fromisoformat(s)
        else:
            # Try common formats
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
                dt = datetime.strptime(s, fmt)
                break
            else:
                dt = None
        if dt:
            return dt.timestamp()
    except Exception:
        pass

    # Fallback: try several strptime attempts
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.timestamp()
        except Exception:
            continue
    return None


def extract_body_from_msg(msg: Message) -> List[Tuple[str, str]]:
    """
    Return all text/plain and text/html payloads from an email as a list of tuples:
    [(content_type, decoded_text), ...]
    Always decodes and ignores attachments.
    """
    bodies: List[Tuple[str, str]] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            dispo = part.get_content_disposition()
            if ctype in ("text/plain", "text/html") and dispo != "attachment":
                try:
                    text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                    bodies.append((ctype, text))
                except Exception:
                    continue
    else:
        ctype = msg.get_content_type()
        try:
            text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
            bodies.append((ctype, text))
        except Exception:
            pass

    return bodies


def expand_addresses(
    server: str,
    port: int,
    addresses: List[str],
) -> List[str]:
    """
    Expand a list of addresses by querying the server for each address.
    Returns a list of expanded addresses.
    """
    expanded_addresses = []

    for addr in addresses:
        try:
            response = requests.get(
                f"http://{server}:{port}/users?filter_by={addr}"
            )
            if response.status_code == 200:
                matches = response.json() or []
                logger.info(f"Server returned {len(matches)} matches for address '{addr}': {matches}.")
                expanded_addresses.extend(matches)
                logger.info(f"Address '{addr}' expanded to: {matches}.")
            else:
                logger.error(f"Failed to expand address '{addr}': {response.json()}.")
        except Exception as e:
            logger.error(f"Error expanding address '{addr}': {e}.")

    expanded_addresses = list(set(expanded_addresses))  # Remove duplicates
    return expanded_addresses


def expand_all_recipients(
    server: str,
    port: int,
    destination: List[str],
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
) -> Tuple[List[str], List[str], List[str]]:
    """
    Expand destination, cc, and bcc lists using regex patterns, querying the server for matching addresses.
    Returns three lists: (expanded_recipients, expanded_cc, expanded_bcc)
    """
    expanded_destination = expand_addresses(server, port, destination)
    expanded_cc = expand_addresses(server, port, cc or [])
    expanded_bcc = expand_addresses(server, port, bcc or [])

    return expanded_destination, expanded_cc, expanded_bcc


# TODO: Implement the following utility functions as needed
# create_message(from, to, subject, body, attachments, headers)
# get_references_headers(original_msg)
