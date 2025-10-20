from email.header import decode_header

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

# TODO: Implement the following utility functions as needed
# parse_mailbox_list()
# save_to_sent_folder()
# create_message(from, to, subject, body, attachments, headers)
# extract_body(msg)
# get_references_headers(original_msg)
