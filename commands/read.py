import argparse
import email
import imaplib
import json
import os
import poplib
import random
import subprocess
import sys
import re
import time
import requests
import webbrowser

from mailbox import Message
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime, timezone

from email import message_from_bytes
from log import get_logger
from config import get_mail_config, set_env_vars_from_args
from connection import connect_mail
from mail_utils import decode_mime_words, parse_datetime_flexible, extract_body_from_msg


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

    # Filtering
    parser.add_argument("--limit", type=int, default=-1, help="Number of emails to read (default: -1 (all)).")
    parser.add_argument("--include-seen", action="store_true", help="Fetch seen and unseen emails (IMAP only). By default, only unseen emails are fetched.")
    parser.add_argument("--sort", choices=["oldest", "newest"], default="oldest", help="Sort order for fetching emails: oldest or newest first (default: oldest).")
    parser.add_argument("--date-since", help="Only fetch emails after YYYY-MM-DD [HH:MM[:SS]] or ISO format.")
    parser.add_argument("--date-before", help="Only fetch emails before YYYY-MM-DD [HH:MM[:SS]] or ISO format.")
    parser.add_argument("--subject-regex", help="Filter by subject regex.")
    parser.add_argument("--body-regex", help="Filter by body regex.")
    parser.add_argument("--from-regex", help="Filter by sender regex.")
    parser.add_argument("--regex-mode", choices=["any", "all"], default="all", help="Combine multiple regex filters using 'any' or 'all' logic (default: all).")
    parser.add_argument("--random", action="store_true", help="Pick one random email among filtered results.")

    # Actions
    parser.add_argument(
        "--action", nargs="+",
        choices=["navigate", "download-attachments", "download-mail", "exec", "open"],
        default=[],
        help="Actions to perform on matching emails (can combine multiple)."
    )
    parser.add_argument(
        "--action-mode",
        choices=["all", "random"],
        default="all",
        help="Whether to execute all matching actions or one random: all, random (default: all)."
    )

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

    results = read_emails(
        mail_config=mail_config,
        limit=args.limit,
        include_seen=args.include_seen,
        sort=args.sort,
        date_since=args.date_since,
        date_before=args.date_before,
        random_pick=args.random,
        subject_regex=args.subject_regex,
        body_regex=args.body_regex,
        from_regex=args.from_regex,
        regex_mode=args.regex_mode,
        actions=args.action,
        action_mode=args.action_mode,
        download_dir=args.download_dir,
        execute_path=args.execute_path,
        pop3_delete=args.pop3_delete
    )

    logger.info(f"Processed {len(results)} emails.")
    return results


def filter_by_regex(subject: str, body: Union[str, List[Tuple[str, str]]], sender: str,
                    subject_re: Optional[str], body_re: Optional[str], from_re: Optional[str],
                    regex_mode: str = "any") -> bool:
    """
    Evaluate regex filters.
    regex_mode: "any" => OR (message matches if any regex matches)
                "all" => AND (message must match all provided regexes)
    If no regex provided, returns True.
    """
    checks = []
    if subject_re:
        checks.append(bool(re.search(subject_re, subject or "", re.IGNORECASE)))
    if body_re:
        if isinstance(body, list):
            body_text = " ".join([text.strip() for _, text in body])
            checks.append(bool(re.search(body_re, body_text or "", re.IGNORECASE)))
        else:
            checks.append(bool(re.search(body_re, body or "", re.IGNORECASE)))
    if from_re:
        checks.append(bool(re.search(from_re, sender or "", re.IGNORECASE)))

    if not checks:
        return True
    if regex_mode == "all":
        return all(checks)
    return any(checks)


def fetch_message_ids_pop3(
    client: Union[poplib.POP3, poplib.POP3_SSL],
    limit: int,
    sort_criteria: str,
    random_pick: bool = False,
) -> List[Dict[str, Any]]:
    """
    Return list of message IDs (UIDs) from POP3 inbox:
    [{"index": int, "uid": str}]
    If UIDL not supported, uses numeric indices.
    """
    ids = []
    try:
        resp, listings, octets = client.uidl()
        for line in listings:
            parts = line.decode().split()
            if len(parts) == 2:
                index, uid = parts
                ids.append({"index": int(index), "uid": uid})
    except poplib.error_proto as e:
        logger.warning(f"UIDL not supported by server: {e}; using numeric indices instead.")

        # Fallback to LIST
        resp, listings, octets = client.list()
        for line in listings:
            parts = line.decode().split()
            if len(parts) >= 1:
                index = parts[0]
                ids.append({"index": int(index), "uid": f"msg-{index}"})

    if not ids:
        logger.info("No emails found in POP3 mailbox.")
        return []

    # Sort order (by default, POP3 returns oldest first)
    ids = list(reversed(ids)) if sort_criteria == "newest" else ids

    if limit > 0:
        ids = ids[:limit]

    if random_pick and ids:
        chosen = [random.choice(ids)]
        logger.info(f"Randomly selected email UID: {chosen[0]['uid']}")
        return chosen

    return ids


def select_messages_pop3(
    client: Union[poplib.POP3, poplib.POP3_SSL],
    limit: int,
    sort: str,
    random_pick: bool,
    regex_mode: str,
    date_since: Optional[str],
    date_before: Optional[str],
    subject_re: Optional[str],
    body_re: Optional[str],
    from_re: Optional[str],
) -> List[Dict[str, Any]]:
    """Select messages from POP3 server according to filters."""
    results: List[Dict[str, Any]] = []

    msg_refs = fetch_message_ids_pop3(client, limit, sort, random_pick)
    if not msg_refs:
        return []

    since_dt = datetime.fromisoformat(date_since) if date_since else None
    before_dt = datetime.fromisoformat(date_before) if date_before else None

    for ref in msg_refs:
        idx, uid = ref["index"], ref["uid"]
        try:
            resp, lines, octets = client.retr(idx)
            raw_msg = b"\r\n".join(lines)
            msg = message_from_bytes(raw_msg)
            body = extract_body_from_msg(msg)

            subject = decode_mime_words(msg.get("Subject", ""))
            sender = email.utils.parseaddr(msg.get("From", ""))[1]
            to = email.utils.parseaddr(msg.get("To", ""))[1]
            date_str = msg.get("Date")

            # Date filtering
            if date_str and (since_dt or before_dt):
                try:
                    msg_dt = email.utils.parsedate_to_datetime(date_str)
                    if msg_dt.tzinfo is not None:
                        msg_dt = msg_dt.astimezone(timezone.utc).replace(tzinfo=None)

                    # Convert user input dates to naive UTC too
                    if since_dt and since_dt.tzinfo is not None:
                        since_dt = since_dt.astimezone(timezone.utc).replace(tzinfo=None)
                    if before_dt and before_dt.tzinfo is not None:
                        before_dt = before_dt.astimezone(timezone.utc).replace(tzinfo=None)

                    if since_dt and msg_dt < since_dt:
                        continue
                    if before_dt and msg_dt > before_dt:
                        continue
                except Exception as e:
                    logger.error(f"Failed to parse date '{date_str}' for message {uid}: {e}")

            # Regex filtering
            if not filter_by_regex(subject, body, sender, subject_re, body_re, from_re, regex_mode):
                continue

            results.append({
                "id": uid,
                "raw_msg": msg,
                "date": date_str,
                "subject": subject,
                "from": sender,
                "to": to,
                "body": body
            })

        except Exception as e:
            logger.warning(f"POP3 fetch failed for message {uid} (index {idx}): {e}")
            continue

    return results


def imap_format_date(date_str: str) -> str:
    """Convert YYYY-MM-DD or other common date formats to IMAP format DD-MMM-YYYY."""
    dt = None
    try:
        dt = datetime.fromisoformat(date_str.strip())
    except ValueError:
        # Fallback to common formats
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                break
            except ValueError:
                dt = None
        if not dt:
            raise ValueError(f"Invalid date format for IMAP: {date_str}")
    # Force English month abbreviations (IMAP requires them)
    return dt.strftime("%d-%b-%Y")


def fetch_message_ids_imap(
    client: imaplib.IMAP4, 
    include_seen: bool,
    limit: int,
    sort_criteria: str,
    random_pick: bool = False,
    date_since: Optional[str] = None,
    date_before: Optional[str] = None
) -> List[bytes]:
    """Return list of message IDs (UIDs) from IMAP inbox (search)."""
    criteria = []
    if include_seen:
        criteria.append("ALL")
    else:
        criteria.append("UNSEEN")
    
    if date_since:
        logger.info(f"Parsing date_since filter: {date_since}")
        imap_date = imap_format_date(date_since)
        logger.info(f"Converted date_since to IMAP format: {imap_date}")
        # date_since = parse_datetime_flexible(date_since)
        # logger.info(f"Parsed date_since: {date_since}")
        criteria.append(f'SINCE "{imap_date}"')
    if date_before:
        imap_date = imap_format_date(date_before)
        criteria.append(f'BEFORE "{imap_date}"')

    query = " ".join(criteria)
    _, data = client.search(None, query)
    ids = data[0].split()
    if not ids:
        logger.info("No emails found with given filters.")
        return []
    
    # Sort order
    # logger.info(f"IDS before sorting: {[id.decode() for id in ids]}")
    ids = list(reversed(ids)) if sort_criteria == "oldest" else ids
    # logger.info(f"IDS after sorting ({sort_criteria}): {[id.decode() for id in ids]}")
    
    if not (limit < 0 or limit > len(ids)):
        ids = ids[:limit]
    
    if random_pick:
        chosen = [random.choice(ids)]
        logger.info(f"Randomly selected email UID: {chosen[0].decode()}")
        return chosen
    return ids


def select_messages_imap(
    client: Union[imaplib.IMAP4, imaplib.IMAP4_SSL],
    include_seen: bool,
    limit: int,
    sort: str,
    random_pick: bool,
    regex_mode: str,
    date_since: Optional[str],
    date_before: Optional[str],
    subject_re: Optional[str],
    body_re: Optional[str],
    from_re: Optional[str],
) -> List[Dict[str, Any]]:
    """Select messages from IMAP server according to filters."""
    results: List[Dict[str, Any]] = []
    
    client.select("INBOX")
    ids = fetch_message_ids_imap(
        client,
        include_seen,
        limit,
        sort,
        random_pick,
        date_since,
        date_before
    )
    if not ids:
        return []

    for mid in ids:
        status, data = client.fetch(mid, "(RFC822)")
        if status != "OK":
            logger.warning(f"Failed to fetch message {mid}")
            continue
        raw = data[0][1]
        msg = message_from_bytes(raw)
        subject = decode_mime_words(msg.get("Subject", ""))
        sender = email.utils.parseaddr(msg.get("From", ""))[1]
        to = email.utils.parseaddr(msg.get("To", ""))[1]
        date = msg.get("Date", "")
        body = extract_body_from_msg(msg)

        if not filter_by_regex(subject, body, sender, subject_re, body_re, from_re, regex_mode):
            logger.warning(f"Message {mid.decode()} skipped by regex filter")
            continue

        results.append({
            "id": mid.decode() if isinstance(mid, bytes) else str(mid), 
            "raw_msg": msg, 
            "date": date,
            "subject": subject, 
            "from": sender, 
            "to": to,
            "body": body
        })

    return results


def select_and_fetch_messages(
    client: Union[imaplib.IMAP4, imaplib.IMAP4_SSL, poplib.POP3, poplib.POP3_SSL, None],
    protocol: str,
    include_seen: bool,
    limit: int,
    sort: str,
    random_pick: bool,
    since: Optional[str],
    before: Optional[str],
    subject_re: Optional[str],
    body_re: Optional[str],
    from_re: Optional[str],
    regex_mode: str,
) -> List[Dict[str, Any]]:
    """
    Select messages according to filters and return list of dicts:
      { "id": str_or_int, "raw_msg": Message, "subject": str, "from": str, "body": str }
    For IMAP: uses server search when possible. For POP3: fetches and filters client-side.
    For MailPit API: fetch items and convert to same structure; some filters client-side.
    """
    results: List[Dict[str, Any]] = []
    # since_ts = parse_datetime_flexible(since) if since else None
    # before_ts = parse_datetime_flexible(before) if before else None

    if protocol == "mailpit":
        logger.warning("MailPit API selected: server-side filtering may be limited; applying client-side filters where possible.")
        raise NotImplementedError("MailPit API message selection not yet implemented.")
        # TODO: implement MailPit API fetching and filtering
        # items = fetch_messages_mailpit_api()
        # for item in items:
        #     # construct minimal message-like dict
        #     subject = item.get("Content", {}).get("Headers", {}).get("Subject", [""])[0]
        #     from_data = item.get("From", {})
        #     sender = f"{from_data.get('Mailbox','')}@{from_data.get('Domain','')}".strip("@")
        #     body = item.get("Content", {}).get("Body", "")
        #     # date handling: try Content.Headers Date
        #     # For regex filtering use body/subject/sender
        #     if not filter_by_regex(subject, body, sender, subject_re, body_re, from_re, regex_mode):
        #         continue
        #     # date filter: best-effort - try headers
        #     # skip date filter if cannot parse
        #     results.append({"id": item.get("ID"), "raw_msg": item, "subject": subject, "from": sender, "body": body})
        # # ordering, limit, random
        # if sort == "oldest":
        #     results = list(reversed(results))  # MailPit returns newest first often
        # if random_pick and results:
        #     return [random.choice(results)]
        # if limit >= 0:
        #     return results[:limit] if limit > 0 else results
        # return results

    elif protocol == "imap":
        return select_messages_imap(
            client,
            include_seen,
            limit,
            sort,
            random_pick,
            regex_mode,
            since,
            before,
            subject_re,
            body_re,
            from_re,
        )

    elif protocol == "pop3":
        logger.warning("POP3 selected: applying all filters client-side; may be inefficient for large mailboxes.")
        return select_messages_pop3(
            client,
            limit,
            sort,
            random_pick,
            regex_mode,
            since,
            before,
            subject_re,
            body_re,
            from_re,
        )
    
    else:
        logger.error(f"Unsupported protocol for selection: {protocol}")
    
    return results


def perform_actions_on_message(
    msg_record: Dict[str, Any],
    actions: List[str],
    download_dir: str,
    execute_path: Optional[str] = None,
    action_mode: str = "all"
) -> Dict[str, Any]:
    """
    Execute requested actions on a single message record.
    Returns result dict with info about performed actions and generated files.
    """
    msg = msg_record["raw_msg"]
    date = msg_record.get("date", "")
    subject = msg_record.get("subject", "")
    sender = msg_record.get("from", "")
    to = msg_record.get("to", "")
    body = msg_record.get("body", "")

    result = {"id": msg_record.get("id"), "date": date,
               "subject": subject, "from": sender, "to": to,
               "performed": []}

    if not actions:
        return result

    # Determine action to execute (for random mode choose one)
    chosen_actions = actions if action_mode == "all" or not actions else [random.choice(actions)]

    for act in chosen_actions:
        try:
            if act == "navigate":
                links = click_links_in_body(body)
                result["performed"].append({"navigated_links": links})
            elif act == "download-attachments":
                saved = download_attachment(msg, download_dir)
                result["performed"].append({"downloaded": saved})
            elif act == "download-mail":
                path = save_full_email(msg, download_dir, subject)
                result["performed"].append({"saved_mail": path})
            elif act == "exec":
                saved = download_attachment(msg, download_dir)
                execute_files(saved, execute_path)
                result["performed"].append({"executed": saved})
            elif act == "open":
                saved = download_attachment(msg, download_dir)
                open_with_default(saved)
                result["performed"].append({"opened": saved})
            else:
                logger.warning(f"Unknown action requested: {act}")
        except Exception as e:
            logger.error(f"Action {act} failed on message {msg_record.get('id')}: {e}")

    return result


def download_attachment(msg: Message, download_dir: str) -> List[str]:
    """Save attachments from `msg` to download_dir. Return list of saved file paths."""
    # TODO: handle MailPit email format if needed
    # Legacy code for MailPit:
    #
    # if isinstance(email_message, dict):  # MailPit email
    #     for attachment in email_message.get('MIME', {}).get('Parts', []):
    #         if 'FileName' in attachment.get('Headers', {}):
    #             filename = attachment['Headers']['FileName'][0]
    #             content = base64.b64decode(attachment['Body'])
    #             filepath = os.path.join(download_dir, filename)
    #             try:
    #                 with open(filepath, 'wb') as f:
    #                     f.write(content)
    #                 logger.info(f"Attachment downloaded: {filepath}")
    #             except Exception as e:
    #                 logger.error(f"Error downloading attachment: {e}")

    saved = []
    os.makedirs(download_dir, exist_ok=True)
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        dispo = part.get_content_disposition()
        if dispo == "attachment" or part.get_filename():
            filename = part.get_filename() or f"attachment_{int(time.time())}"
            filename = os.path.basename(filename)
            path = os.path.join(download_dir, filename)
            try:
                with open(path, "wb") as f:
                    f.write(part.get_payload(decode=True))
                logger.info(f"Attachment downloaded: {path}")
                saved.append(path)
            except Exception as e:
                logger.error(f"Failed to download attachment {filename}: {e}")
    return saved


def click_links_in_body(body: Union[str, List[Tuple[str, str]]]) -> List[str]:
    """Open all http(s) links found in body in default browser. Return list of opened links."""
    if isinstance(body, list):
        body = " ".join([text.strip() for _, text in body])
    
    links = re.findall(r"https?://[^\s\"'<>]+", body)
    links_list = []
    if not links:
        logger.info("No links found in message body.")
    for link in links:
        try:
            if link in links_list:
                continue  # Avoid duplicates

            logger.info(f"Opening link: {link}")
            links_list.append(link)
            webbrowser.open(link)
        except Exception as e:
            logger.error(f"Failed to open link {link}: {e}")
    
    return links_list


def save_full_email(msg: Message, download_dir: str, subject: str) -> str:
    """Save the full email as .eml in download_dir. Return filepath."""
    os.makedirs(download_dir, exist_ok=True)
    fname = f"{subject}.eml"
    path = os.path.join(download_dir, fname)
    try:
        with open(path, "wb") as f:
            f.write(msg.as_bytes())
        logger.info(f"Saved full email to: {path}")
        return path
    except Exception as e:
        logger.error(f"Failed to save full email: {e}")
        raise


def execute_files(filepaths: List[str], execute_path: Optional[str] = None):
    """Run each file in list as a subprocess (be cautious)."""
    for p in filepaths:
        p = os.path.abspath(p)
        try:
            if execute_path:
                dest_path = os.path.join(execute_path, os.path.basename(p))
                os.makedirs(execute_path, exist_ok=True)
                os.rename(p, dest_path)
                p = dest_path
                logger.info(f"Moved file to execution path: {dest_path}.")
            
            if not os.access(p, os.X_OK):
                logger.info(f"Setting execute permissions for: {p}.")
                os.chmod(p, 0o755)
            
            logger.info(f"Executing {p}.")
            subprocess.run([p], check=False)
            logger.info(f"Execution completed for {p}.")
        except Exception as e:
            logger.error(f"Execution failed for {p}: {e}")


def open_with_default(filepaths: List[str]):
    """Open files with default OS application (xdg-open on Linux)."""
    for p in filepaths:
        p = os.path.abspath(p)
        try:
            logger.info(f"Opening with default app: {p}.")
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", p])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", p])
            else:
                # Assume Windows
                os.startfile(p)
        except Exception as e:
            logger.error(f"Failed to open {p} with default program: {e}.")


def read_emails(
    mail_config: Dict[str, Any],
    limit: int = -1,
    include_seen: bool = False,
    sort: str = "oldest",
    random_pick: bool = False,
    date_since: Optional[str] = None,
    date_before: Optional[str] = None,
    subject_regex: Optional[str] = None,
    body_regex: Optional[str] = None,
    from_regex: Optional[str] = None,
    regex_mode: str = "any",
    actions: Optional[List[str]] = None,
    action_mode: str = "all",
    download_dir: Optional[str] = None,
    execute_path: Optional[str] = None,
    pop3_delete: bool = False
) -> List[Dict[str, Any]]:
    """Read emails from the mail server and process them.
    Returns list of processed message dicts (with performed action info)."""
    if download_dir:
        download_dir = os.path.abspath(os.path.expanduser(download_dir))
    else:
        download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    results_all: List[Dict[str, Any]] = []

    client, protocol = connect_mail(mail_config)
    if not client and protocol != "api":
        logger.error("Failed to connect to mail server.")
        sys.exit(1)

    selected = select_and_fetch_messages(
        client,
        protocol,
        include_seen,
        limit=limit,
        sort=sort,
        random_pick=random_pick,
        since=date_since,
        before=date_before,
        subject_re=subject_regex,
        body_re=body_regex,
        from_re=from_regex,
        regex_mode=regex_mode,
    )

    logger.info(f"Selected {len(selected)} emails for processing.")
    # for email_data in selected:
    #     res_id = email_data.get("id")
    #     res_raw_msg = email_data.get("raw_msg")
    #     res_subject = email_data.get("subject")
    #     res_from = email_data.get("from")
    #     res_body = email_data.get("body", "")
    #     logger.info(f"Processing email ID {res_id} from {res_from} with subject {res_subject} and body: {res_body}...")
    # sys.exit(0)

    for record in selected:
        action_result = perform_actions_on_message(record, actions or [], download_dir, execute_path, action_mode)
        results_all.append({**record, "actions": action_result.get("performed")})

        # POP3 deletion if requested
        if protocol == "pop3" and pop3_delete:
            try:
                client.dele(int(record["id"]) + 1)
                logger.info(f"Deleted POP3 message index {record['id']}")
            except Exception as e:
                logger.error(f"Failed to delete POP3 message {record['id']}: {e}")

    # Cleanup and logout
    try:
        if protocol == "imap" and client:
            try:
                client.close()
            except Exception as e:
                logger.warning(f"Failed to close IMAP mailbox: {e}")
            client.logout()
        elif protocol == "pop3" and client:
            try:
                client.quit()
            except Exception as e:
                logger.warning(f"Failed to quit POP3 session: {e}")
    except Exception as e:
        logger.error(f"Error during logout/cleanup: {e}")

    return results_all
    
    # logger.info("Checking for new emails...")
    # new_emails = fetch_emails(mail, protocol)
    
    # if not new_emails:
    #     logger.info("No new emails found.")
    # else:
    #     for email_data in new_emails:
    #         process_email(mail, email_data, protocol, download_dir, action_type, action_pattern, execute_path, pop3_delete)
    
    # if protocol == 'pop3':
    #     mail.quit()
    # elif protocol == 'imap':
    #     mail.close()
    #     mail.logout()


# LEGACY / DEPRECATED FUNCTIONS BELOW. To be removed in future versions.

# Deprecated function: fetch_emails
#
# def fetch_emails(
#     client: Union[imaplib.IMAP4, imaplib.IMAP4_SSL, poplib.POP3, poplib.POP3_SSL],
#     protocol: str
# ):
#     """Fetch email list from the server, depending on protocol."""
#     if protocol == "api":
#         try:
#             response = requests.get("http://localhost:8025/api/v2/messages")
#             if response.status_code == 200:
#                 messages = response.json()
#                 logger.info(f"Found {messages['count']} messages using MailPit API")
#                 logger.debug(f"Raw MailPit API response: {json.dumps(messages, indent=2)}")
#                 return messages['items']
#             else:
#                 logger.error(f"Error fetching emails from MailPit API: {response.status_code}")
#                 return []
#         except Exception as e:
#             logger.error(f"Error fetching emails from MailPit API: {e}")
#             return []
#     else:
#         try:
#             if protocol == 'pop3':
#                 num_messages = len(client.list()[1])
#                 logger.info(f"Found {num_messages} messages using POP3")
#                 return range(num_messages)
#             elif protocol == 'imap':
#                 _, message_numbers = client.search(None, 'UNSEEN')  # _, message_numbers = mail.search(None, 'ALL')
#                 num_messages = len(message_numbers[0].split())
#                 logger.info(f"Found {num_messages} messages using IMAP")
#                 return message_numbers[0].split()
#         except Exception as e:
#             logger.error(f"Error fetching emails: {e}")
#             return []


# Deprecated function: process_email
#
# def process_email(
#     client: Union[imaplib.IMAP4, imaplib.IMAP4_SSL, poplib.POP3, poplib.POP3_SSL],
#     email_data: Any,
#     protocol: str,
#     download_dir: str,
#     action_type: Optional[str] = None,
#     action_pattern: Optional[str] = None,
#     execute_path: Optional[str] = None,
#     pop3_delete: bool = False
# ):
#     """Process a single email: download, parse, and take actions."""
#     try:
#         if protocol == "mailpit":
#             logger.debug(f"Processing MailPit email: {json.dumps(email_data, indent=2)}")

#             subject = email_data['Content']['Headers'].get('Subject', ['No Subject'])[0]
#             from_data = email_data['From']
#             sender = f"{from_data['Mailbox']}@{from_data['Domain']}"
#             body = email_data['Content']['Body']

#             logger.info(f"Processing MailPit email from {sender} with subject: {subject}")
#             process_content(subject, body, email_data, download_dir, action_type, action_pattern, execute_path)
#             return
        
#         if protocol == 'pop3':
#             logger.info(f"Fetching POP3 message ID {email_data + 1}")

#             # Download the email
#             status, lines, octets = client.retr(email_data + 1)
#             if status.startswith(b'+OK'):
#                 raw_email = b"\n".join(lines)
#             else:
#                 logger.error(f"Failed to retrieve POP3 email ID {email_data + 1}")
#                 return
#         elif protocol == 'imap':
#             logger.info(f"Fetching IMAP message ID {email_data.decode()}")

#             # Download the email
#             status, msg_data = client.fetch(email_data, '(RFC822)')
#             if status != 'OK':
#                 logger.error(f"Failed to fetch IMAP email ID {email_data.decode()}")
#                 return
#             raw_email = msg_data[0][1]
#         else:
#             logger.error(f"Unsupported protocol: {protocol}")
#             return

#         # Decode email
#         msg = message_from_bytes(raw_email)

#         # Get metadata
#         subject = decode_mime_words(msg.get("Subject"))
#         sender = email.utils.parseaddr(msg.get("From"))[1]
#         logger.info(f"Processing email from {sender} with subject: {subject}")

#         # Walk through email parts
#         if msg.is_multipart():
#             logger.info("Processing multipart email...")
#             for part in msg.walk():
#                 content_type = part.get_content_type()
#                 disposition = part.get_content_disposition()
                
#                 # HTML or plain text parts
#                 if content_type in ("text/plain", "text/html") and disposition != "attachment":
#                     body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
#                     process_content(subject, body, msg, download_dir, action_type, action_pattern, execute_path)

#                 # Attachments
#                 elif disposition == "attachment":
#                     filename = part.get_filename()
#                     if filename:
#                         filepath = os.path.join(download_dir, filename)
#                         with open(filepath, "wb") as f:
#                             f.write(part.get_payload(decode=True))
#                         logger.info(f"Saved attachment: {filepath}")
#         else:
#             logger.info("Processing non-multipart email...")
#             body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
#             process_content(subject, body, msg, download_dir, action_type, action_pattern, execute_path)

#         if protocol == 'pop3' and pop3_delete:
#             try:
#                 client.dele(email_data + 1)
#                 logger.info(f"Deleted POP3 message ID {email_data + 1} after processing.")
#             except Exception as e:
#                 logger.error(f"Failed to delete POP3 message ID {email_data + 1}: {e}")
#     except Exception as e:
#         logger.error(f"Error processing email ID {email_data.decode()}: {e}", exc_info=True)
