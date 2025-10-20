import imaplib
import time

from email.header import decode_header
from typing import Dict, List, Union
from email import message_from_bytes
from email.utils import parsedate_tz, mktime_tz

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


# TODO: Implement the following utility functions as needed
# create_message(from, to, subject, body, attachments, headers)
# extract_body(msg)
# get_references_headers(original_msg)
