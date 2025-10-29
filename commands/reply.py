#!/usr/bin/env python3
import argparse
import os

from typing import Any, Dict, List, Optional
from email import message_from_bytes
from email.utils import make_msgid, getaddresses

from log import get_logger
from config import get_mail_config, get_smtp_config, set_env_vars_from_args
from commands.read import read_emails
from commands.send import build_email_message, send_prepared_email, build_template_email_message
from mail_utils import extract_body_from_msg, expand_all_recipients


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
    parser.add_argument("--send-separately", action="store_true", help="Send individual emails to each recipient instead of a single email to all recipients.")
    parser.add_argument("--use-regex", action="store_true", help="Enable regex parsing in destination, cc and bcc addresses. Useful for bulk sending, spam or phishing simulations.")
    parser.add_argument("--api-host", type=str, help="API server address for regex expansion of email addresses when --use-regex is enabled. If not provided, defaults to SMTP host.")
    parser.add_argument("--api-port", type=int, default=9999, help="API server port for regex expansion of email addresses when --use-regex is enabled.")

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
    
    # Get recipients if regex is used
    if args.use_regex:
        if not args.api_host:
            args.api_host = args.smtp_host
        
        args.reply_to, args.cc, args.bcc = expand_all_recipients(
            server=args.api_host,
            port=args.api_port,
            destination=args.reply_to,
            cc=args.cc,
            bcc=args.bcc
        )
        
        # Exclude sender from recipient lists if present
        if args.sender in args.reply_to:
            args.reply_to.remove(args.sender)
        if args.sender in args.cc:
            args.cc.remove(args.sender)
        if args.sender in args.bcc:
            args.bcc.remove(args.sender)

        logger.info(f"Final reply_to list: {args.reply_to}")
        logger.info(f"Final CC list: {args.cc}")
        logger.info(f"Final BCC list: {args.bcc}")
    
    logger.debug(f"ARGS: {args}")
    logger.info(f"Preparing to reply to {len(messages)} message(s)...")

    for msg_record in messages:
        try:
            reply_email(
                original_msg_record=msg_record,
                sender=args.sender,
                reply_to=args.reply_to,
                subject=args.subject,
                body=args.body,
                body_file=args.body_file,
                body_images=args.body_image,
                attachments=args.attach,
                cc=args.cc,
                bcc=args.bcc,
                template_name=args.template,
                template_params=args.template_params,
                use_template_subject=args.use_template_subject,
                no_quote_original=args.no_quote_original,
                reply_all=args.reply_all,
                save_sent=args.save_sent
            )
        except Exception as e:
            logger.error(f"Failed to reply to '{msg_record.get('subject', '')}': {e}.")

    logger.info("Reply operation completed.")


def reply_email(
    original_msg_record: Dict[str, Any],
    sender: str,
    reply_to: Optional[List[str]] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    body_file: Optional[str] = None,
    body_images: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    template_name: Optional[str] = None,
    template_params: Optional[Dict[str, Any]] = None,
    use_template_subject: bool = False,
    no_quote_original: bool = False,
    reply_all: bool = False,
    save_sent: bool = False,
    body_type: str = "html"
):
    msg_record = original_msg_record
    if reply_to is None:
        reply_to = []
    
    raw_msg = msg_record["raw_msg"]
    msg = message_from_bytes(raw_msg.as_bytes())

    orig_subject = msg_record.get("subject", "")
    orig_sender = msg_record.get("from", "")
    orig_to = msg_record.get("to", "")
    orig_date = msg_record.get("date", "")
    msg_id = msg.get("Message-ID", make_msgid(domain=sender.split("@")[-1]))

    # Subject
    if subject:
        reply_subject = subject
    elif orig_subject.lower().startswith("re:"):
        reply_subject = orig_subject
    else:
        reply_subject = f"Re: {orig_subject}"

    # Body
    new_bodies = []
    bodies = extract_body_from_msg(msg)

    if no_quote_original:
        if template_name:
            template_dict = build_template_email_message(template_name, template_params)
            reply_body = template_dict.get("body", "")
            if use_template_subject:
                reply_subject = template_dict.get("subject", reply_subject)
        elif body_file:
            logger.info(f"Reading body from file: {body_file}")
            try:
                with open(os.path.expanduser(body_file), "r", encoding="utf-8") as f:
                    file_body = f.read()
                    logger.info(f"Read body from file: {file_body[:100]}...")
                    reply_body = file_body
            except Exception as e:
                logger.error(f"Failed to read body from file '{body_file}': {e}. Using empty body.")
                reply_body = ""
        elif body:
            reply_body = body
        else:
            reply_body = ""
        
        new_bodies.append((f"text/{body_type}", reply_body))
    else:
        logger.info("Quoting original message in reply body...")
        logger.info(f"Bodies extracted: {bodies}")
        quoted_text = ""
        if bodies:
            if template_name:
                template_dict = build_template_email_message(template_name, template_params)
                template_body = template_dict.get("body", "")
                new_body = ("text/html", template_body)
                if use_template_subject:
                    reply_subject = template_dict.get("subject", reply_subject)
            elif body_file:
                logger.info(f"Reading body from file: {body_file}")
                try:
                    with open(os.path.expanduser(body_file), "r", encoding="utf-8") as f:
                        file_body = f.read()
                        logger.info(f"Read body from file: {file_body[:100]}...")
                        new_body = ("text/html", file_body)
                except Exception as e:
                    logger.error(f"Failed to read body from file '{body_file}': {e}. Using empty body.")
                    new_body = ("text/html", "")
            else:  #  body:
                new_body = ("text/html", body)
            
            # Check if bodies contain plain text or HTML
            has_html = any(c == "text/html" for c, b in bodies)

            if has_html:
                quoted_text = "<br>".join(b for c, b in bodies)
                reply_body = ("text/html",
                    f"<br><br><blockquote style='margin-left:1em; border-left:2px solid #ccc; padding-left:1em;'>"
                    f"On {orig_date}, {orig_sender} wrote:<br>{quoted_text}</blockquote>"
                )
            else:
                quoted_text = "\n".join(b for c, b in bodies)
                quoted_lines = "\n".join(f"> {line}" for line in quoted_text.splitlines())
                reply_body = ("text/plain",
                    f"{quoted_text}\n\nOn {orig_date}, {orig_sender} wrote:\n{quoted_lines}")
                
            
            new_bodies.append(new_body)
            new_bodies.append(reply_body)


        #     plain = next((b for c, b in bodies if c == "text/plain"), None)
        #     html = next((b for c, b in bodies if c == "text/html"), None)
        #     logger.info(f"Plain text body to quote: {plain}")
        #     if plain:
        #         quoted_lines = "\n".join(f"> {line}" for line in plain.splitlines())
        #         quoted_text = f"\n\nOn {orig_date}, {orig_sender} wrote:\n{quoted_lines}"
        #     elif html:
        #         # Keep HTML format, quote lines
        #         quoted_text = (
        #             f"<br><br><blockquote style='margin-left:1em; border-left:2px solid #ccc; padding-left:1em;'>"
        #             f"On {orig_date}, {orig_sender} wrote:<br>{html}</blockquote>"
        #         )

        # reply_body = (body or "") + quoted_text

    # Recipients
    if reply_all:
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
        if reply_to:
            all_addrs.extend(reply_to)
        
        # Remove duplicates and the sender
        sender_addr = sender.lower()
        all_addrs = list({a.lower(): a for a in all_addrs}.values())
        all_addrs = [a for a in all_addrs if a.lower() != sender_addr]

        reply_to_list = all_addrs
    else:
        logger.info("Replying only to the original sender...")
        if reply_to:
            reply_to_list = reply_to
        else:
            reply_to_list: List[str] = msg_record.get("reply_to") or [msg_record["from"]]


    logger.info(f"Reply recipients: {reply_to_list}")

    all_recipients = reply_to_list[:]
    if cc:
        all_recipients.extend(cc)
    if bcc:
        all_recipients.extend(bcc)

    logger.info(f"All recipients (To, CC, BCC): {all_recipients}")


    # Build reply message
    built_msg = build_email_message(
        sender=sender,
        destination=reply_to_list,
        subject=reply_subject,
        body=new_bodies,
        body_file=body_file,
        body_images=body_images,
        attachments=attachments,
        cc=cc,
        template_name=template_name,
        template_params=template_params
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
        sender=sender,
        all_recipients=all_recipients,
        save_sent=save_sent,
    )

    logger.info(f"Successfully replied to '{all_recipients}' ({orig_subject}).")
