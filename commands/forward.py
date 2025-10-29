#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional
from email import message_from_bytes

from log import get_logger
from config import get_mail_config, get_smtp_config, set_env_vars_from_args
from commands.read import read_emails, save_full_email
from commands.send import build_email_message, send_prepared_email, build_template_email_message
from mail_utils import save_to_sent_folder, extract_body_from_msg, expand_all_recipients

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
    parser.add_argument("destination", nargs="*", help="Recipient email address/addresses.")
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
    
    # Get recipients if regex is used
    if args.use_regex:
        if not args.api_host:
            args.api_host = args.smtp_host
        
        args.destination, args.cc, args.bcc = expand_all_recipients(
            server=args.api_host,
            port=args.api_port,
            destination=args.destination,
            cc=args.cc,
            bcc=args.bcc
        )
        
        # Exclude sender from recipient lists if present
        if args.sender in args.destination:
            args.destination.remove(args.sender)
        if args.sender in args.cc:
            args.cc.remove(args.sender)
        if args.sender in args.bcc:
            args.bcc.remove(args.sender)

        logger.info(f"Final recipient list: {args.destination}")
        logger.info(f"Final CC list: {args.cc}")
        logger.info(f"Final BCC list: {args.bcc}")

    to_addresses = args.destination # [addr.strip() for addr in args.to.split(",") if addr.strip()]
    if not to_addresses:
        logger.error("No valid recipient addresses provided.")
        sys.exit(1)

    logger.info(f"Preparing to forward {len(messages)} message(s) to {', '.join(to_addresses)}")

    for msg_record in messages:
        print(f"Msg record: {msg_record}")
        try:
            forward_email(
                original_msg_record=msg_record,
                sender=args.sender,
                to_addresses=to_addresses,
                subject=args.subject,
                subject_prefix=args.subject_prefix,
                body=args.body,
                body_file=args.body_file,
                body_images=args.body_image,
                attachments=args.attach,
                cc=args.cc,
                bcc=args.bcc,
                template_name=args.template,
                template_params=args.template_params,
                use_template_subject=args.use_template_subject,
                mode=args.mode,
                no_attachments=args.no_attachments,
                save_sent=args.save_sent
            )
        except Exception as e:
            logger.error(f"Failed to forward message '{msg_record.get('subject', '')}': {e}")

    logger.info("Forwarding completed.")


def forward_email(
    original_msg_record: Dict[str, Any],
    sender: str,
    to_addresses: List[str],
    subject: Optional[str] = None,
    subject_prefix: str = "Fwd:",
    body: Optional[str] = None,
    body_file: Optional[str] = None,
    body_images: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    template_name: Optional[str] = None,
    template_params: Optional[Dict[str, Any]] = None,
    use_template_subject: bool = False,
    mode: str = "inline",
    no_attachments: bool = False,
    save_sent: bool = False,
):
    """Forward a single email message."""
    msg_record = original_msg_record
    if attachments is None:
        attachments = []

    raw_msg = msg_record["raw_msg"]
    msg = message_from_bytes(raw_msg.as_bytes())

    orig_date = msg_record.get("date", "")
    orig_subject: str = msg_record.get("subject", "")
    orig_sender = msg_record.get("from", "")
    orig_to = msg_record.get("to", "")

    if subject:
        fwd_subject = subject
    elif orig_subject.startswith(subject_prefix) or orig_subject.startswith("Fwd:"):
        fwd_subject = orig_subject
    else:
        fwd_subject = f"{subject_prefix} {orig_subject}".strip()

    # Prepare inline forward
    if mode == "inline":
        bodies = extract_body_from_msg(msg)
        forward_text = ("text/html",
            f"<br><br>---------- Forwarded message ---------<br>"
            f"From: {orig_sender}<br>"
            f"Date: {orig_date}<br>"
            f"Subject: {orig_subject}<br>"
            f"To: {', '.join(orig_to)}<br><br>"
        )
        bodies.insert(0, forward_text)

        # Check if template is used
        if template_name:
            template_dict = build_template_email_message(template_name, template_params)
            template_body = template_dict.get("body", "")
            bodies.insert(0, ("text/html", template_body))
            if use_template_subject:  # Use template subject if requested
                logger.info("Using subject from template.")
                fwd_subject = template_dict.get("subject", fwd_subject)
                logger.info(f"New subject: {fwd_subject}")
        elif body_file:
            logger.info(f"Reading body from file: {body_file}")
            try:
                with open(os.path.expanduser(body_file), "r", encoding="utf-8") as f:
                    file_body = f.read()
                    logger.info(f"Read body from file: {file_body[:100]}...")
                    new_body = ("text/html", file_body)
                    bodies.insert(0, new_body)
            except Exception as e:
                logger.error(f"Failed to read body file '{body_file}': {e}")
        elif body:
            new_body = ("text/html", body or "")
            bodies.insert(0, new_body)
        else:
            logger.warning("No body, body file, or template provided for inline forward. Only original message will be included.")
        

        # inline_body = ""
        # if bodies:
        #     plain = next((b for c, b in bodies if c == "text/plain"), None)
        #     html = next((b for c, b in bodies if c == "text/html"), None)
        #     inline_body = plain or html or ""
        # # own_body = template or body or ""
        # forward_text = (
        #     f"{body or ''}"
        #     f"<br><br>---------- Forwarded message ---------<br>"
        #     f"From: {orig_sender}<br>"
        #     f"Date: {orig_date}<br>"
        #     f"Subject: {orig_subject}<br>"
        #     f"To: {orig_to}<br><br>"
        #     f"{inline_body}"
        # )
        # print(fwd_subject)
        # print()
        # print(forward_text)
        # print()

        # Extract attachments unless disabled
        forwarded_attachments: List[str] = []
        if not no_attachments:
            for part in msg.walk():
                dispo = part.get_content_disposition()
                if dispo == "attachment":
                    filename = part.get_filename()
                    if not filename:
                        continue
                    filepath = os.path.join(tempfile.gettempdir(), filename)
                    with open(os.path.join(tempfile.gettempdir(), filename), "wb") as f:
                        f.write(part.get_payload(decode=True))
                    forwarded_attachments.append(filepath)
                    logger.info(f"Temporarily saved attachment: {filepath}")
                    # with tempfile.NamedTemporaryFile(delete=False, prefix="fwd_", suffix=f"_{filename}") as f:
                    #     f.write(part.get_payload(decode=True))
                    #     attachments.append(f.name)
                    #     logger.info(f"Temporarily saved attachment: {f.name}")

        # TODO: Send separately if requested

        logger.info("Forwarding inline...")
        built_msg = build_email_message(
            sender=sender,
            destination=to_addresses,
            subject=fwd_subject,
            body=bodies,
            body_images=body_images,
            attachments=attachments + forwarded_attachments,
            cc=cc
        )

        all_recipients = to_addresses[:]
        if cc:
            all_recipients.extend(cc)
        if bcc:
            all_recipients.extend(bcc)

        logger.info("Forwarding inline email...")
        send_prepared_email(
            msg=built_msg,
            smtp_config=get_smtp_config(include_imap=True),
            sender=sender,
            all_recipients=all_recipients,
            save_sent=save_sent,
        )

        for path in forwarded_attachments:
            try:
                os.remove(path)
            except Exception:
                logger.warning(f"Failed to remove temporary attachment file: {path}")

    elif mode == "attachment":                
        filepath = save_full_email(raw_msg, tempfile.gettempdir(), orig_subject)
        logger.info(f"Temporarily saved forwarded email as attachment: {filepath}")

        if template_name and use_template_subject:
            template_dict = build_template_email_message(template_name, template_params)
            fwd_subject = template_dict.get("subject", fwd_subject)

        built_msg = build_email_message(
            sender=sender,
            destination=to_addresses,  # destination
            subject=fwd_subject,
            body=body,
            body_file=body_file,
            body_images=body_images,
            attachments=[filepath],
            cc=cc,
            template_name=template_name,
            template_params=template_params,
        )

        all_recipients = to_addresses[:]
        if cc:
            all_recipients.extend(cc)
        if bcc:
            all_recipients.extend(bcc)
        
        logger.info("Forwarding as attachment...")
        send_prepared_email(
            msg=built_msg,
            smtp_config=get_smtp_config(include_imap=True),
            sender=sender,
            all_recipients=all_recipients,
            save_sent=save_sent,
        )
        
        try:
            os.remove(filepath)
        except Exception:
            logger.warning(f"Failed to remove temporary .eml file: {filepath}")

    logger.info(f"Successfully forwarded message '{fwd_subject}' to {', '.join(to_addresses)}")
