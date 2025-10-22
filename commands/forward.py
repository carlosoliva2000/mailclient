#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
from typing import List
from email import message_from_bytes

from log import get_logger
from config import get_mail_config, get_smtp_config, set_env_vars_from_args
from commands.read import read_emails, save_full_email
from commands.send import build_email_message, send_prepared_email
from mail_utils import save_to_sent_folder, extract_body_from_msg

logger = get_logger()


def register_arguments(parser: argparse.ArgumentParser):
    """Register CLI arguments for the forward command."""
    parser.add_argument("--smtp-host", "-H", required=True, help="SMTP host.")
    parser.add_argument("--smtp-port", "-P", type=int, required=True, help="SMTP port.")
    parser.add_argument("--smtp-username", "-u", default=None, help="SMTP username. Not required if no authentication is needed.")
    parser.add_argument("--smtp-password", "-p", default=None, help="SMTP password. Not required if no authentication is needed.")
    parser.add_argument("--smtp-security", "-S", choices=["none", "starttls", "ssl"], default="none", help="Type of SMTP connection: none, starttls, ssl (default: none).")
    parser.add_argument("--allow-insecure-tls", "-I", action="store_true", default=False, help="Allow unverified/self-signed TLS certificates.")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="SMTP connection timeout in seconds (default: 30).")
    parser.add_argument("--pop3-delete", action="store_true", default=False, help="Delete emails from server after downloading (POP3 only).")
    parser.add_argument("--save-sent", action="store_true", default=False, help="Save a copy of the sent email to the 'Sent' folder (requires IMAP).")
    parser.add_argument("--mail-host", help="IMAP host for saving sent emails (default: same as SMTP host).")
    parser.add_argument("--mail-port", type=int, default=993, help="IMAP port (default: 993).")
    parser.add_argument("--mail-protocol", "-r", choices=["imap", "pop3", "mailpit"], default="imap", help="Mail protocol to use: imap, pop3, mailpit (default: imap). Mailpit is for local testing servers like MailPit.")
    parser.add_argument("--mail-username", help="IMAP username (default: same as SMTP username).")
    parser.add_argument("--mail-password", help="IMAP password (default: same as SMTP password).")
    parser.add_argument("--mail-folder", default="Sent", help="IMAP folder name to save sent email (default: Sent).")
    parser.add_argument("sender", help="Sender email address.")
    parser.add_argument("destination", nargs="+", help="Recipient email address/addresses.")
    parser.add_argument("--subject", help="Email subject. If used, overrides the forwarded email subject with prefix.  If used with --template, overrides template subject.")
    parser.add_argument("--body", help="Email body text.")
    parser.add_argument("--body-file", help="File containing email body text. If provided, overrides 'body'.")
    parser.add_argument("--body-image", action="append", help="Paths to inline image files. You can specify this argument as many images as needed.")
    parser.add_argument("--attach", action="append", help="Paths to attachment files. You can specify this argument as many attachments as needed.")
    parser.add_argument("--cc", action="append", help="CC recipient email addresses. You can specify this argument as many addresses as needed.")
    parser.add_argument("--bcc", action="append", help="BCC recipient email addresses. You can specify this argument as many addresses as needed.")
    parser.add_argument("--template", help="Email template name to use.",
                        choices=[
                            "phishing_login", 
                            "new_corporate_email", 
                            "mail_2", 
                            "mail_3", 
                            "mail_4", 
                            "mail_5", 
                            "mail_6", 
                            "mail_7", 
                            "mail_8", 
                            "mail_9", 
                            "mail_10", 
                            "mail_11", 
                            "mail_12"
                        ])
    parser.add_argument("--template-params", help="JSON string of template parameters, e.g. '{\"username\": \"john.doe\", \"reset_link\": \"http://example.com/reset\"}'. "
                        "Depends on the template used.")
    parser.add_argument("--use-template-subject", action="store_true", help="Use the subject defined in the template instead of prepending 'Fwd:' to the original subject.")

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

    # Forward-specific options
    parser.add_argument(
        "--mode",
        choices=["inline", "attachment"],
        default="inline",
        help="Forward mode: inline (include original body) or attachment (.eml attached). Default: inline."
    )
    parser.add_argument(
        "--subject-prefix",
        default="Fwd:",
        help="Prefix to prepend to forwarded email subjects (default: Fwd:)."
    )
    parser.add_argument(
        "--no-attachments",
        action="store_true",
        help="Do NOT include the original attachments when forwarding inline."
    )


def forward_email_cli(args: argparse.Namespace):
    """Entry point for the forward command."""
    # Set env vars
    set_env_vars_from_args(args, [
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
        "SMTP_SECURITY", "ALLOW_INSECURE_TLS", "TIMEOUT",
        # Read settings
        "MAIL_HOST", "MAIL_PORT", "MAIL_PROTOCOL", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_FOLDER"
    ])
    
    mail_config = get_mail_config()
    print(mail_config)

    # Read filtered messages
    logger.info("Fetching messages to forward...")
    messages = read_emails(
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

    if not messages:
        logger.info("No messages matched filters. Nothing to forward.")
        return

    to_addresses = args.destination # [addr.strip() for addr in args.to.split(",") if addr.strip()]
    if not to_addresses:
        logger.error("No valid recipient addresses provided.")
        sys.exit(1)

    logger.info(f"Preparing to forward {len(messages)} message(s) to {', '.join(to_addresses)}")

    for msg_record in messages:
        print(f"Msg record: {msg_record}")
        try:
            raw_msg = msg_record["raw_msg"]
            msg = message_from_bytes(raw_msg.as_bytes())

            date = msg_record.get("date", "")
            subject = msg_record.get("subject", "")
            sender = msg_record.get("from", "")
            to = msg_record.get("to", "")
            fwd_subject = f"{args.subject_prefix} {subject}".strip()

            attachments: List[str] = []

            # Prepare inline forward
            if args.mode == "inline":
                # TODO: fix body extraction to handle multipart properly
                # build_email_message should handle multipart messages
                # so that method should take either string or Message or List[Tuple[str, str]] like extract_body_from_msg
                # Right now templates cannot be used with forwarding inline because of this
                
                bodies = extract_body_from_msg(msg)
                inline_body = ""
                if bodies:
                    plain = next((b for c, b in bodies if c == "text/plain"), None)
                    html = next((b for c, b in bodies if c == "text/html"), None)
                    inline_body = plain or html or ""
                # own_body = args.template or args.body or ""
                forward_text = (
                    f"{args.body or ''}"
                    f"<br><br>---------- Forwarded message ---------<br>"
                    f"From: {sender}<br>"
                    f"Date: {date}<br>"
                    f"Subject: {subject}<br>"
                    f"To: {to}<br><br>"
                    f"{inline_body}"
                )
                # print(fwd_subject)
                # print()
                # print(forward_text)
                # print()

                # Extract attachments unless disabled
                if not args.no_attachments:
                    for part in msg.walk():
                        dispo = part.get_content_disposition()
                        if dispo == "attachment":
                            filename = part.get_filename()
                            if not filename:
                                continue
                            filepath = os.path.join(tempfile.gettempdir(), filename)
                            with open(os.path.join(tempfile.gettempdir(), filename), "wb") as f:
                                f.write(part.get_payload(decode=True))
                            attachments.append(filepath)
                            logger.info(f"Temporarily saved attachment: {filepath}")
                            # with tempfile.NamedTemporaryFile(delete=False, prefix="fwd_", suffix=f"_{filename}") as f:
                            #     f.write(part.get_payload(decode=True))
                            #     attachments.append(f.name)
                            #     logger.info(f"Temporarily saved attachment: {f.name}")

                logger.info("Forwarding inline...")
                built_msg = build_email_message(
                    sender=args.sender,
                    destination=to_addresses,
                    subject=fwd_subject,
                    body=forward_text,
                    body_file=None,
                    body_images=args.body_image,
                    attachments=attachments,
                    cc=args.cc,
                    template_name=args.template,
                    template_params=args.template_params,
                )

                all_recipients = to_addresses[:]
                if args.cc:
                    all_recipients.extend(args.cc)
                if args.bcc:
                    all_recipients.extend(args.bcc)

                logger.info("Forwarding inline email...")
                send_prepared_email(
                    msg=built_msg,
                    smtp_config=get_smtp_config(include_imap=True),
                    sender=args.sender,
                    all_recipients=all_recipients,
                    save_sent=args.save_sent,
                )

                for path in attachments:
                    try:
                        os.remove(path)
                    except Exception:
                        logger.warning(f"Failed to remove temporary attachment file: {path}")

            elif args.mode == "attachment":                
                filepath = save_full_email(raw_msg, tempfile.gettempdir(), subject)
                logger.info(f"Temporarily saved forwarded email as attachment: {filepath}")

                built_msg = build_email_message(
                    sender=args.sender,
                    destination=args.destination,
                    subject=fwd_subject,
                    body=args.body,
                    body_file=args.body_file,
                    body_images=args.body_image,
                    attachments=[filepath],
                    cc=args.cc,
                    template_name=args.template,
                    template_params=args.template_params,
                )

                all_recipients = to_addresses[:]
                if args.cc:
                    all_recipients.extend(args.cc)
                if args.bcc:
                    all_recipients.extend(args.bcc)
                
                logger.info("Forwarding as attachment...")
                send_prepared_email(
                    msg=built_msg,
                    smtp_config=get_smtp_config(include_imap=True),
                    sender=args.sender,
                    all_recipients=all_recipients,
                    save_sent=args.save_sent,
                )
                
                try:
                    os.remove(filepath)
                except Exception:
                    logger.warning(f"Failed to remove temporary .eml file: {filepath}")

            logger.info(f"Successfully forwarded message '{subject}' to {', '.join(to_addresses)}")

            # Cleanup temp attachments
            for path in attachments:
                try:
                    os.remove(path)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to forward message '{msg_record.get('subject', '')}': {e}")

    logger.info("Forwarding completed.")
