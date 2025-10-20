import argparse
import sys
from commands import send, read  # , reply, forward
from log import get_logger, setup_global_logger
# from mailclient.commands import send, read, reply, forward
# from mailclient.log import get_logger

# logger = get_logger()

def main():
    parser = argparse.ArgumentParser(prog="mailclient", description="Unified email client CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- SEND ---
    send_parser = subparsers.add_parser("send", help="Send an email.")
    send.register_arguments(send_parser)

    # --- READ ---
    # read_parser = subparsers.add_parser("read", help="Read emails.")
    # read.register_arguments(read_parser)

    # --- REPLY ---
    # reply_parser = subparsers.add_parser("reply", help="Reply to emails.")
    # reply.register_arguments(reply_parser)

    # # --- FORWARD ---
    # forward_parser = subparsers.add_parser("forward", help="Forward emails.")
    # forward.register_arguments(forward_parser)

    args, unknown = parser.parse_known_args()

    # Logging setup
    setup_global_logger(debug=getattr(args, "debug", False))
    logger = get_logger()
    
    logger.info("Starting mailclient.")
    if args.debug:
        logger.info("Debug mode is enabled.")

    if args.command == "send":
        send.send_email(args)
    elif args.command == "read":
        # read.main(args)
        pass
    # elif args.command == "reply":
    #     reply.main(args)
    # elif args.command == "forward":
    #     forward.main(args)
    else:
        parser.print_help()
        sys.exit(1)

    logger.info("Finishing mailclient.")

if __name__ == "__main__":
    main()
