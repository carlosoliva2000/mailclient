#!/usr/bin/env python3
import argparse
import os
from typing import List
from email import message_from_bytes
from email.utils import make_msgid, getaddresses

from log import get_logger
from config import get_mail_config, get_smtp_config, set_env_vars_from_args
from commands.read import read_emails
from commands.send import build_email_message, send_prepared_email
from mail_utils import extract_body_from_msg


logger = get_logger()


def register_arguments(parser: argparse.ArgumentParser):
    """Register CLI arguments for the reply command."""
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
    parser.add_argument("reply_to", nargs="*", default=[], help="Optional override of recipient email address(es). If not provided, uses the original email's From field.")

    parser.add_argument("--subject", help="Override subject (otherwise uses 'Re: <original subject>'). If used with --template, overrides template subject as well.")
    parser.add_argument("--body", help="Email body text.")
    parser.add_argument("--body-file", help="File containing email body text. If provided, overrides --body.")
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
    parser.add_argument("--use-template-subject", action="store_true", help="Use the subject defined in the template instead of prepending 'Re:' to the original subject.")

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

    # Reply-specific options
    # parser.add_argument("--include-original-attachments", action="store_true", help="Include the attachments from the original message in the reply.")
    parser.add_argument("--no-quote-original", action="store_true", help="Do not include quoted original text in the reply body.")
    parser.add_argument("--reply-all", action="store_true", help="Reply to all recipients instead of only the sender.")


def reply_email_cli(args: argparse.Namespace):
    """Entry point for the reply command."""
    set_env_vars_from_args(args, [
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
        "SMTP_SECURITY", "ALLOW_INSECURE_TLS", "TIMEOUT",
        # Read settings
        "MAIL_HOST", "MAIL_PORT", "MAIL_PROTOCOL", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_FOLDER"
    ])

    mail_config = get_mail_config()

    logger.info("Fetching messages to reply to...")
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
    )

    if not messages:
        logger.info("No messages matched filters. Nothing to reply to.")
        return
    
    logger.info(f"ARGS: {args}")
    logger.info(f"Preparing to reply to {len(messages)} message(s)...")

    for msg_record in messages:
        try:
            raw_msg = msg_record["raw_msg"]
            msg = message_from_bytes(raw_msg.as_bytes())

            orig_subject = msg_record.get("subject", "")
            orig_sender = msg_record.get("from", "")
            orig_to = msg_record.get("to", "")
            orig_date = msg_record.get("date", "")
            msg_id = msg.get("Message-ID", make_msgid())

            # Subject
            if args.subject:
                reply_subject = args.subject
            # elif args.use_template_subject and args.template:
            # TODO: re-enable template subject usage
            #     fwd_subject = get_template(args.template).get("subject", subject)
            elif orig_subject.lower().startswith("re:"):
                reply_subject = orig_subject
            else:
                reply_subject = f"Re: {orig_subject}"

            # Body
            bodies = extract_body_from_msg(msg)
            if args.no_quote_original:
                reply_body = args.template or args.body_file or args.body or ""
                # TODO: If template is used, load template body
            else:
                logger.info("Quoting original message in reply body...")
                logger.info(f"Bodies extracted: {bodies}")
                quoted_text = ""
                if bodies:
                    plain = next((b for c, b in bodies if c == "text/plain"), None)
                    html = next((b for c, b in bodies if c == "text/html"), None)
                    logger.info(f"Plain text body to quote: {plain}")
                    if plain:
                        quoted_lines = "\n".join(f"> {line}" for line in plain.splitlines())
                        quoted_text = f"\n\nOn {orig_date}, {orig_sender} wrote:\n{quoted_lines}"
                    elif html:
                        # Keep HTML format, quote lines
                        quoted_text = (
                            f"<br><br><blockquote style='margin-left:1em; border-left:2px solid #ccc; padding-left:1em;'>"
                            f"On {orig_date}, {orig_sender} wrote:<br>{html}</blockquote>"
                        )

                reply_body = (args.body or "") + quoted_text

            # Attachments
            attachments: List[str] = []
            # if args.include_original_attachments:
            #     for part in msg.walk():
            #         if part.get_content_disposition() == "attachment":
            #             filename = part.get_filename()
            #             if not filename:
            #                 continue
            #             path = os.path.join(tempfile.gettempdir(), filename)
            #             with open(path, "wb") as f:
            #                 f.write(part.get_payload(decode=True))
            #             attachments.append(path)
            #             logger.info(f"Included original attachment: {path}")

            if args.attach:
                attachments.extend(args.attach)

            # Recipients
            if args.reply_all:
                logger.info("Replying to all original recipients...")
                all_addrs = []

                # Prioritize Reply-To if present
                if msg_record.get("reply_to"):
                    all_addrs.extend(msg_record["reply_to"])
                else:
                    all_addrs.append(msg_record["from"])
                
                # Include To + CC from original message
                for field in ["to", "cc"]:
                    all_addrs.extend(msg_record.get(field, []))

                # Include any additional addresses specified in command line
                if args.reply_to:
                    all_addrs.extend(args.reply_to)
                
                # Remove duplicates and the sender
                sender_addr = args.sender.lower()
                all_addrs = list({a.lower(): a for a in all_addrs}.values())
                all_addrs = [a for a in all_addrs if a.lower() != sender_addr]

                reply_to = all_addrs
            else:
                logger.info("Replying only to the original sender...")
                if args.reply_to:
                    reply_to = args.reply_to
                else:
                    reply_to = msg_record.get("reply_to") or [msg_record["from"]]


            logger.info(f"Reply recipients: {reply_to}")

            all_recipients = reply_to[:]
            if args.cc:
                all_recipients.extend(args.cc)
            if args.bcc:
                all_recipients.extend(args.bcc)

            logger.info(f"All recipients (To, CC, BCC): {all_recipients}")


            # Build reply message
            built_msg = build_email_message(
                sender=args.sender,
                destination=reply_to,
                subject=reply_subject,
                body=reply_body,
                body_file=args.body_file,
                body_images=args.body_image,
                attachments=attachments,
                cc=args.cc,
                template_name=args.template,
                template_params=args.template_params
            )

            # Add threading headers
            built_msg["In-Reply-To"] = msg_id
            existing_refs = msg.get_all("References", [])
            refs = " ".join(existing_refs + [msg_id])
            built_msg["References"] = refs

            # Send email
            logger.info(f"Replying to {orig_sender} with subject '{reply_subject}'...")
            send_prepared_email(
                msg=built_msg,
                smtp_config=get_smtp_config(include_imap=True),
                sender=args.sender,
                all_recipients=all_recipients,
                save_sent=args.save_sent,
            )

            logger.info(f"Successfully replied to '{all_recipients}' ({orig_subject}).")

            for path in attachments:
                try:
                    os.remove(path)
                except Exception:
                    logger.warning(f"Failed to remove temporary attachment file: {path}.")

        except Exception as e:
            logger.error(f"Failed to reply to '{msg_record.get('subject', '')}': {e}.")

    logger.info("Reply operation completed.")
