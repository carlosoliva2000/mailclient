import argparse
import os
import mimetypes
import smtplib

# from contextlib import redirect_stdout
from typing import List, Optional, Dict, Any
from email import encoders, message_from_binary_file
from email.utils import encode_rfc2231, formatdate, make_msgid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.message import MIMEMessage

from email_templates import get_template
from log import get_logger
from config import get_smtp_config, set_env_vars_from_args
from connection import connect_smtp, connect_mail
from mail_utils import save_to_sent_folder, expand_all_recipients


logger = get_logger()


def register_arguments(parser: argparse.ArgumentParser):
    """Register command-line arguments for the send command."""
    parser.add_argument("--smtp-host", "-H", required=True, help="SMTP host.")
    parser.add_argument("--smtp-port", "-P", type=int, required=True, help="SMTP port.")
    parser.add_argument("--smtp-username", "-u", default=None, help="SMTP username. Not required if no authentication is needed.")
    parser.add_argument("--smtp-password", "-p", default=None, help="SMTP password. Not required if no authentication is needed.")
    parser.add_argument("--smtp-security", "-S", choices=["none", "starttls", "ssl"], default="none", help="Type of SMTP connection: none, starttls, ssl (default: none).")
    parser.add_argument("--allow-insecure-tls", "-I", action="store_true", default=False, help="Allow unverified/self-signed TLS certificates.")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="SMTP connection timeout in seconds (default: 30).")
    parser.add_argument("--save-sent", action="store_true", default=False, help="Save a copy of the sent email to the 'Sent' folder (requires IMAP).")
    parser.add_argument("--mail-host", help="IMAP host for saving sent emails (default: same as SMTP host).")
    parser.add_argument("--mail-port", type=int, default=993, help="IMAP port (default: 993).")
    parser.add_argument("--mail-username", help="IMAP username (default: same as SMTP username).")
    parser.add_argument("--mail-password", help="IMAP password (default: same as SMTP password).")
    parser.add_argument("--mail-folder", default="Sent", help="IMAP folder name to save sent email (default: Sent).")
    parser.add_argument("sender", help="Sender email address.")
    parser.add_argument("destination", nargs="*", help="Recipient email address/addresses. If wildcards are needed (only * and ?), use --use-regex.")
    parser.add_argument("--subject", help="Email subject. If used with --template, overrides template subject.")
    parser.add_argument("--body", help="Email body text.")
    parser.add_argument("--body-file", help="File containing email body text. If provided, overrides 'body'.")
    parser.add_argument("--body-image", action="append", help="Paths to inline image files. You can specify this argument as many images as needed.")
    parser.add_argument("--attach", action="append", help="Paths to attachment files. You can specify this argument as many attachments as needed.")
    parser.add_argument("--cc", action="append", help="CC recipient email addresses. You can specify this argument as many addresses as needed. If wildcards are needed (only * and ?), use --use-regex.")
    parser.add_argument("--bcc", action="append", help="BCC recipient email addresses. You can specify this argument as many addresses as needed. If wildcards are needed (only * and ?), use --use-regex.")
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
    parser.add_argument("--send-separately", action="store_true", help="Send individual emails to each recipient instead of a single email to all recipients.")
    parser.add_argument("--use-regex", action="store_true", help="Enable regex parsing in destination, cc and bcc addresses. Useful for bulk sending, spam or phishing simulations.")
    parser.add_argument("--api-host", type=str, help="API server address for regex expansion of email addresses when --use-regex is enabled. If not provided, defaults to SMTP host.")
    parser.add_argument("--api-port", type=int, default=9999, help="API server port for regex expansion of email addresses when --use-regex is enabled.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode.", required=False)


def send_email_cli(args: argparse.Namespace):
    """Send an email using SMTP through CLI arguments."""
    
    # Set env vars from CLI args
    set_env_vars_from_args(args, [
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
        "SMTP_SECURITY", "ALLOW_INSECURE_TLS", "TIMEOUT",
        # IMAP settings for saving sent emails
        "MAIL_HOST", "MAIL_PORT", "MAIL_USERNAME", "MAIL_PASSWORD", 
        "MAIL_SECURITY", "MAIL_FOLDER"
    ])

    smtp_config = get_smtp_config(include_imap=args.save_sent)

    logger.debug(f"SMTP Configuration: {smtp_config}")

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

    # Send separately if requested
    if args.send_separately:
        for recipient in args.destination:
            # Build message for each recipient
            msg = build_email_message(
                sender=args.sender,
                destination=[recipient],
                subject=args.subject,
                body=args.body,
                body_file=args.body_file,
                body_images=args.body_image,
                attachments=args.attach,
                cc=args.cc,
                template_name=args.template,
                template_params=args.template_params
            )

            # Prepare recipients list
            all_recipients = [recipient]
            if args.cc:
                all_recipients.extend(args.cc)
            if args.bcc:
                all_recipients.extend(args.bcc)

            # Send email
            send_prepared_email(
                msg=msg,
                smtp_config=smtp_config,
                sender=args.sender,
                all_recipients=all_recipients,
                save_sent=args.save_sent
            )
        return

    # Build message
    msg = build_email_message(
        sender=args.sender,
        destination=args.destination,
        subject=args.subject,
        body=args.body,
        body_file=args.body_file,
        body_images=args.body_image,
        attachments=args.attach,
        cc=args.cc,
        template_name=args.template,
        template_params=args.template_params
    )

    # Prepare recipients list
    all_recipients = args.destination[:]
    if args.cc:
        all_recipients.extend(args.cc)
    if args.bcc:
        all_recipients.extend(args.bcc)
    
    # Send email
    send_prepared_email(
        msg=msg,
        smtp_config=smtp_config,
        sender=args.sender,
        all_recipients=all_recipients,
        save_sent=args.save_sent
    )

    # send_email(
    #     sender=args.sender,
    #     destination=args.destination,
    #     subject=args.subject,
    #     body=args.body,
    #     body_file=args.body_file,
    #     body_images=args.body_image,
    #     attachments=args.attach,
    #     cc=args.cc,
    #     bcc=args.bcc,
    #     template_name=args.template,
    #     template_params=args.template_params,
    #     smtp_config=smtp_config,
    #     save_sent=args.save_sent
    # )


def build_email_message(
    sender: str,
    destination: List[str],
    subject: Optional[str],
    body: Optional[str] = None,
    body_file: Optional[str] = None,
    body_images: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
    cc: Optional[List[str]] = None,
    template_name: Optional[str] = None,
    template_params: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> MIMEMultipart:
    """
    Build an email message (MIME) with optional templates, attachments, inline images, etc.
    Returns a ready-to-send MIMEMultipart object.
    """
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(destination)
    if cc:
        msg["Cc"] = ", ".join(cc)

    # Subject, body and template handling
    if template_name:
        try:
            template = get_template(template_name, **(template_params or {}))
            subject = subject or template.get("subject", "")
            body = template.get("body") or body
        except ValueError as e:
            logger.error(f"Error using template: {e}")
            raise ValueError(f"Error using template: {e}")
        
    msg["Subject"] = subject or "No Subject"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])

    # Body handling
    if body is None and body_file is None:
        mail_body = ""
        logger.warning("Email body is empty.")
    elif body_file:
        try:
            with open(os.path.expanduser(body_file), "r", encoding="utf-8") as f:
                mail_body = f.read()
        except IOError as e:
            logger.error(f"Error reading body file: {e}")
            raise IOError(f"Error reading body file: {e}")
    elif body:
        mail_body = body
    else:
        mail_body = ""

    msg.attach(MIMEText(mail_body, "html"))

    # Inline images
    if body_images:
        for path in body_images:
            path = os.path.abspath(os.path.expanduser(path))
            try:
                with open(path, "rb") as f:
                    img = MIMEImage(f.read())
                    img.add_header("Content-ID", f"<{os.path.basename(path)}>")
                    img.add_header("Content-Disposition", "inline", filename=os.path.basename(path))
                    msg.attach(img)
            except FileNotFoundError as e:
                logger.error(f"Body image not found: {path}")
                raise FileNotFoundError(f"Body image not found: {path}")
            except Exception as e:
                logger.error(f"Error attaching image {path}: {e}")
                raise Exception(f"Error attaching image {path}: {e}")
    
    # Attachments
    if attachments:
        for path in attachments:
            path = os.path.abspath(os.path.expanduser(path))
            try:
                ctype, encoding = mimetypes.guess_type(path)
                logger.info(f"Attaching file {path} with guessed type {ctype} and encoding {encoding}")

                # Fallback to binary if type is unknown
                if ctype is None:
                    ctype = "application/octet-stream"

                maintype, subtype = ctype.split("/", 1)
                logger.info(f"Attachment maintype: {maintype}, subtype: {subtype}")

                filename = os.path.basename(path)
                safe_filename = ("utf-8", "", encode_rfc2231(filename))

                if maintype == "message" and subtype == "rfc822":
                    # Special handling for .eml files
                    with open(path, "rb") as f:
                        eml_msg = message_from_binary_file(f)
                    part = MIMEMessage(eml_msg)
                    part.add_header("Content-Disposition", "attachment", filename=safe_filename)

                elif maintype == "text":
                    # Handle text files with UTF-8 fallback
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            text = f.read()
                    except UnicodeDecodeError:
                        with open(path, "r", encoding="latin1", errors="ignore") as f:
                            text = f.read()
                    part = MIMEText(text, _subtype=subtype)
                    part.add_header("Content-Disposition", "attachment", filename=safe_filename)

                else:
                    # Binary attachments
                    with open(path, "rb") as f:
                        part = MIMEBase(maintype, subtype)
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", "attachment", filename=safe_filename)

                msg.attach(part)
            except FileNotFoundError:
                logger.error(f"Attachment file not found: {path}.")
                raise FileNotFoundError(f"Attachment file not found: {path}.")
            except Exception as e:
                logger.error(f"Error attaching file {path}: {e}.")
                raise Exception(f"Error attaching file {path}: {e}.")

    # Extra headers (for reply/forward)
    if extra_headers:
        for key, value in extra_headers.items():
            msg[key] = value

    return msg


def send_prepared_email(
    msg: MIMEMultipart,
    smtp_config: Dict[str, Any],
    sender: str,
    all_recipients: List[str],
    save_sent: bool = False
) -> bool:
    """Send a pre-built email and optionally save it to the 'Sent' folder."""
    try:
        with connect_smtp(smtp_config) as server:
            server.send_message(msg, from_addr=sender, to_addrs=all_recipients)
        logger.info("Email sent successfully!")

        if save_sent:
            imap_config = smtp_config["imap_config"]
            imap_client, _ = connect_mail(imap_config)
            save_to_sent_folder(
                imap_client=imap_client,
                sent_folder=imap_config.get("folder", "Sent"),
                msg_bytes=msg.as_bytes()
            )
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication error: {e}")
        return False
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP connection error: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error occurred: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error trying to send email: {e}")
        return False


def send_email(
    sender: str,
    destination: List[str],
    subject: Optional[str],
    smtp_config: Dict[str, Any],
    body: Optional[str] = None,
    body_file: Optional[str] = None,
    body_images: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    template_name: Optional[str] = None,
    template_params: Optional[Dict[str, str]] = None,
    save_sent: bool = False
) -> bool:
    """
    Send an email with:
    - Subject and body (from text or file) or using a template (if subject is provided, it overrides template subject).
    - Optional inline images in the body.
    - Optional attachments.
    - Optional CC and BCC recipients.
    - Optional link to be added to the body.
    - Optional template parameters in JSON format. Depends on the template used.
    - Optional debug mode.

    Args:
        sender (str): Sender email address.
        destination (List[str]): List of recipient email addresses.
        subject (str): Email subject. If used with template, overrides template subject.
        smtp_config (Dict[str, Any]): SMTP configuration dictionary. See mailclient.config.get_smtp_config() for details.
        body (Optional[str]): Email body text.
        body_file (Optional[str]): Path to file containing email body text. If provided, overrides 'body'.
        body_images (Optional[List[str]]): List of paths to inline image files.
        attach_path (Optional[List[str]]): List of paths to attachment files.
        cc (Optional[List[str]]): List of CC recipient email addresses.
        bcc (Optional[List[str]]): List of BCC recipient email addresses.
        template_name (Optional[str]): Name of the email template to use.
        template_params (Optional[Dict[str, str]]): Parameters for the email template.
        debug (bool): Enable debug mode.

    Returns:
        bool: True if email sent successfully, False otherwise.
    """

    # Prepare message
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(destination)

    if cc:
        msg["Cc"] = ", ".join(cc)

    all_recipients = destination[:]
    if cc:
        all_recipients.extend(cc)
    if bcc:
        all_recipients.extend(bcc)

    # Template handling
    if template_name:
        try:
            template = get_template(template_name, **(template_params or {}))
            subject = subject or template.get("subject", "")
            body = body or template.get("body", "")
        except ValueError as e:
            logger.error(f"Error using template: {e}")
            return False

    # Body handling
    if body is None and body_file is None:
        email_body = ""
        logger.warning("Email body is empty.")
    elif body_file:
        try:
            with open(os.path.abspath(os.path.expanduser(body_file)), "r") as f:
                email_body = f.read()
        except Exception as e:
            logger.error(f"Error reading body file: {e}")
            return False
    elif body:
        email_body = body
    else:
        email_body = ""

    # if add_link:
    #     email_body += f"\n\nPlease check this link: {add_link}"

    # Set email headers and body
    msg["Subject"] = subject or "No Subject"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.attach(MIMEText(email_body, "html"))

    # Attachments
    if attachments:
        for path in attachments:
            path = os.path.abspath(os.path.expanduser(path))
            ctype, encoding = mimetypes.guess_type(path)
            maintype, subtype = (ctype or 'application/octet-stream').split('/', 1)
            try:
                with open(path, "rb") as f:
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(f.read())

                    # Encode the payload using Base64
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", "attachment", filename=os.path.basename(path))
                    msg.attach(part)
            except FileNotFoundError:
                logger.error(f"Attachment file not found: {path}.")
                return False
            except Exception as e:
                logger.error(f"Error attaching file {path}: {e}.")
                return False

    # Inline images
    if body_images:
        for path in body_images:
            path = os.path.abspath(os.path.expanduser(path))
            try:
                with open(path, "rb") as f:
                    img = MIMEImage(f.read())
                    img.add_header("Content-ID", f"<{os.path.basename(path)}>")
                    img.add_header("Content-Disposition", "inline", filename=os.path.basename(path))
                    msg.attach(img)
            except FileNotFoundError:
                logger.error(f"Body image not found: {path}.")
                return False
            except Exception as e:
                logger.error(f"Error adding image {path}: {e}.")
                return False

    # Send email
    try:
        with connect_smtp(smtp_config) as server:
            server.send_message(msg, from_addr=sender, to_addrs=all_recipients)
        logger.info("Email sent successfully!")

        if save_sent:
            imap_config = smtp_config["imap_config"]
            imap_client, _ = connect_mail(imap_config)
            save_to_sent_folder(
                imap_client=imap_client,
                sent_folder=imap_config.get("folder", "Sent"),
                msg_bytes=msg.as_bytes()
            )
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


# def __send_email(
#     sender: str,
#     destination: List[str],
#     subject: Optional[str],
#     body: Optional[str] = None,
#     body_file: Optional[str] = None,
#     body_images: Optional[List[str]] = None,
#     attachs: Optional[List[str]] = None,
#     add_link: Optional[str] = None,
#     cc: Optional[List[str]] = None,
#     bcc: Optional[List[str]] = None,
#     template_name: Optional[str] = None,
#     template_params: Optional[Dict[str, str]] = None,
#     debug: Optional[bool]=False,
# ) -> bool:
#     """
#     Send an email with optional attachment, CC, link, and template.

#     Args:
#         sender (str): Sender's email address.
#         destination (List[str]): List of recipient email addresses.
#         subject (str): Email subject.
#         body (Optional[str]): Email body text.
#         body_file (Optional[str]): Path to file containing email body text. If provided, overrides 'body'.
#         body_images (Optional[List[str]]): List of paths to inline image files.
#         attach_path (Optional[List[str]]): List of paths to attachment files.
#         cc (Optional[List[str]]): List of CC recipient email addresses.
#         bcc (Optional[List[str]]): List of BCC recipient email addresses.
#         add_link (Optional[str]): URL to be added to the email body.
#         template_name (Optional[str]): Name of the email template to use.
#         template_params (Optional[Dict[str, str]]): Parameters for the email template.
#         smtp_security (Optional[str]): Type of SMTP connection:
#             - 'none' = no encryption.
#             - 'starttls' = STARTTLS (explicit TLS).
#             - 'ssl' = implicit SSL/TLS.
#             Defaults to None.
#         allow_insecure_tls (bool): Allow unverified/self-signed TLS certificates.
#         debug (bool): Enable debug mode.

#     Returns:
#         bool: True if email sent successfully, False otherwise.
#     """
#     config = get_email_config()
#     logger.info(f"Email configuration: {config}")

#     smtp_security = config["smtp_security"]

#     msg = MIMEMultipart()
#     msg["From"] = sender
#     msg["To"] = ", ".join(destination)

#     if cc:
#         msg["Cc"] = ", ".join(cc)

#     all_recipients = destination[:]
#     if cc:
#         all_recipients.extend(cc)
#     if bcc:
#         all_recipients.extend(bcc)

#     if template_name:
#         try:
#             template = get_template(template_name, **(template_params or {}))
#             template_subject = template.get("subject", "")
#             body = template.get("body", "")
#             subject = (
#                 subject or template_subject
#             )  # Allow overriding subject if provided explicitly
#         except ValueError as e:
#             logger.error(f"Error using template: {e}")
#             return False

#     msg["Subject"] = subject or "No Subject"
#     msg["Date"] = formatdate(localtime=True)
#     msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])

#     if body is None and body_file is None:
#         body = ""
#         logger.warning("Email body is empty.")
#     elif body and body_file:
#         logger.warning("Both body text and body file provided. Using body file content.")
#         body = ""
    
#     if body_file:
#         try:
#             body_file = os.path.abspath(os.path.expanduser(body_file))
#             with open(body_file, "r") as bf:
#                 body = bf.read()
#         except Exception as e:
#             logger.error(f"Error reading body file: {e}")
#             return False

#     if add_link:
#         body += f"\n\nPlease check out this link: {add_link}"

#     msg.attach(MIMEText(body, "html"))

#     if attachs:
#         attachs = [os.path.abspath(os.path.expanduser(p)) for p in attachs]
#         for attach_path in attachs:
#             try:
#                 ctype, encoding = mimetypes.guess_type(attach_path)
#                 maintype, subtype = (ctype or 'application/octet-stream').split('/', 1)
#                 with open(attach_path, "rb") as file:
#                     part = MIMEBase(maintype, subtype)
#                     part.set_payload(file.read())

#                     # Encode the payload using Base64
#                     encoders.encode_base64(part)
#                     part.add_header(
#                         "Content-Disposition",
#                         "attachment",
#                         filename=os.path.basename(attach_path),
#                     )
#                     msg.attach(part)
#             except FileNotFoundError:
#                 logger.error(f"Attachment file not found: {attach_path}")
#                 return False
#             except Exception as e:
#                 logger.error(f"Error attaching file: {e}")
#                 return False

#     # Attach body inline image
#     if body_images:
#         for im_path in body_images:
#             im_path = os.path.abspath(os.path.expanduser(im_path))
#             try:
#                 with open(im_path, "rb") as img_file:
#                     img = MIMEImage(img_file.read())
#                     img.add_header(
#                         "Content-ID", f"<{os.path.basename(im_path)}>"
#                     )
#                     img.add_header(
#                         "Content-Disposition",
#                         "inline",
#                         filename=os.path.basename(im_path),
#                     )
#                     msg.attach(img)
#             except FileNotFoundError:
#                 logger.error(f"Body image not found: {im_path}")
#                 return False
#             except Exception as e:
#                 logger.error(f"Error adding image: {e}")
#                 return False

#     context = ssl.create_default_context()
#     if config["allow_insecure_tls"]:
#         logger.warning("Insecure TLS connections allowed (self-signed/unverified certificates).")
#         context.check_hostname = False
#         context.verify_mode = ssl.CERT_NONE

#     try:
#         if smtp_security == "ssl":
#             logger.info("Connecting with implicit TLS/SSL (SMTP_SSL)")
#             server_class = smtplib.SMTP_SSL
#             server_kwargs = {"context": context}
#         else:
#             logger.info("Connecting with standard SMTP")
#             server_class = smtplib.SMTP
#             server_kwargs = {}

#         with server_class(
#             config["smtp_host"], 
#             config["smtp_port"], 
#             timeout=config["timeout"],
#             **server_kwargs
#         ) as server:
#             if debug:
#                 with io.StringIO() as buffer:
#                     with redirect_stdout(buffer):
#                         server.set_debuglevel(1)
#                     logger.debug(buffer.getvalue())
#                 # pass
#                 # FIXME: The line below blocks the execution of GHOSTS
#                 # TODO: find a way to redirect the output to the log file
#                 # instead of the stdout/stderr
#                 # server.set_debuglevel(1)
            
#             server.ehlo()
#             if smtp_security == "starttls":
#                 logger.info("Starting STARTTLS session")
#                 server.starttls(context=context)
#                 server.ehlo()

#             if config["smtp_username"] and config["smtp_password"]:
#                 server.login(config["smtp_username"], config["smtp_password"])

#             server.send_message(msg, from_addr=sender, to_addrs=all_recipients)
#         logger.info("Email sent successfully!")
#         return True
#     except smtplib.SMTPAuthenticationError as e:
#         logger.error(f"SMTP authentication error: {e}")
#         return False
#     except smtplib.SMTPConnectError as e:
#         logger.error(f"SMTP connection error: {e}")
#         return False
#     except smtplib.SMTPException as e:
#         logger.error(f"SMTP error occurred: {e}")
#         return False
#     except Exception as e:
#         logger.error(f"Unexpected error: {e}", exc_info=True)
#         return False


# def main():
#     """
#     Main function to parse command-line arguments and send an email.
#     """
#     parser = argparse.ArgumentParser(
#         description="Send an email with optional attachment, CC, link, and template."
#     )

#     parser.add_argument(
#         "--smtp-host", "-H", help="SMTP host", required=True
#     )
#     parser.add_argument(
#         "--smtp-port",
#         "-P",
#         type=int,
#         help="SMTP port",
#         required=True,
#     )
#     parser.add_argument(
#         "--smtp-username",
#         "-u",
#         help="SMTP username. Not required if no authentication is needed.",
#         default=None
#     )
#     parser.add_argument(
#         "--smtp-password", 
#         "-p",
#         help="SMTP password. Not required if no authentication is needed.",
#         default=None
#     )
#     parser.add_argument(
#         "--smtp-security",
#         "-S",
#         choices=["none", "starttls", "ssl"],
#         help="Type of SMTP connection: none, starttls, ssl",
#         default="none"
#     )
#     parser.add_argument(
#         "--allow-insecure-tls",
#         "-I",
#         action="store_true",
#         help="Allow unverified/self-signed TLS certificates",
#         default=False,
#     )
#     parser.add_argument(
#         "--timeout",
#         "-t",
#         type=int,
#         help="SMTP connection timeout in seconds (default: 30)",
#         default=30
#     )

#     parser.add_argument("sender", help="Sender's email address")
#     parser.add_argument("destination", nargs="+", help="Recipient email address(es)")
#     parser.add_argument("--subject", help="Email subject")
#     parser.add_argument("--body", help="Email body text")
#     parser.add_argument("--body-file", help="Path to file containing email body text")
#     parser.add_argument("--body-image", action="append", help="Inline image file paths")
#     parser.add_argument("--attach", action="append", help="Path to attachment files")
#     parser.add_argument("--add-link", help="URL to be added to the email body")
#     parser.add_argument("--cc", action="append", help="CC recipient email addresses")
#     parser.add_argument("--bcc", action="append", help="BCC recipient email addresses")
#     parser.add_argument("--template", help="Name of the email template to use",
#                         choices=[
#                             "phishing_login", 
#                             "new_corporate_email", 
#                             "mail_2", 
#                             "mail_3", 
#                             "mail_4", 
#                             "mail_5", 
#                             "mail_6", 
#                             "mail_7", 
#                             "mail_8", 
#                             "mail_9", 
#                             "mail_10", 
#                             "mail_11", 
#                             "mail_12"
#                         ])
#     parser.add_argument(
#         "--template-params",
#         help="JSON string of parameters for the email template",
#     )
#     parser.add_argument(
#         "--debug",
#         action="store_true",
#         help="Enable debug mode.",
#         required=False,
#     )


#     args, unknown = parser.parse_known_args()

#     if args.debug:
#         console_handler.setFormatter(formatter)
#     else:
#         console_handler.setFormatter(LevelBasedFormatter())
#         console_handler.setLevel(logging.INFO)

#     logger.info("Starting send_email")
#     if unknown:
#         logger.warning(f"Unknown arguments ignored: {unknown}")

#     # Set environment variables from command-line arguments
#     set_env_vars(args)

#     template_params = {}
#     if args.template_params:
#         try:
#             template_params = json.loads(args.template_params)
#         except json.JSONDecodeError:
#             logger.error("Invalid JSON for template parameters")
#             logger.info("Finishing send_email with errors")
#             sys.exit(1)

#     logger.info(
#         f"Sending email from {args.sender} to {args.destination}."
#     )
#     if not send_email(
#         sender=args.sender,
#         destination=args.destination,
#         subject=args.subject,
#         body=args.body,
#         body_file=args.body_file,
#         body_images=args.body_image,
#         attachs=args.attach,
#         add_link=args.add_link,
#         cc=args.cc,
#         bcc=args.bcc,
#         template_name=args.template,
#         template_params=template_params,
#         debug=args.debug,
#     ):
#         logger.error("Failed to send email")
#         logger.info("Finishing send_email with errors")
#         sys.exit(1)
#     else:
#         logger.info("Email sent successfully")
#         logger.info("Finishing send_email")

# if __name__ == "__main__":
#     main()
