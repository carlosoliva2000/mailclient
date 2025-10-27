import requests
import argparse

from typing import Dict, Tuple

from log import get_logger


logger = get_logger()

def register_arguments(parser: argparse.ArgumentParser):
    """Register command-line arguments for the passwd command."""
    parser.add_argument(
        "username",
        type=str,
        # required=True,
        help="Username to change password for.",
    )
    parser.add_argument(
        "new_password",
        type=str,
        # required=True,
        help="New password.",
    )

    parser.add_argument(
        "--server",
        type=str,
        required=True,
        help="API server address.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9999,
        help="API server port.",
    )


def passwd_cli(args: argparse.Namespace):
    """Handle the passwd command."""
    username = args.username
    password = args.new_password
    server = args.server
    port = args.port

    change_password(
        username=username,
        new_password=password,
        server=server,
        port=port
    )


def change_password(
    username: str,
    new_password: str,
    server: str,
    port: int,
) -> Tuple[bool, Dict]:
    """Change password for the provided user."""
    logger.info(f"Changing password for user '{username}' to '{new_password}' on server '{server}:{port}'")

    # Send a POST request to /update-password endpoint
    url = f"http://{server}:{port}/update-password"
    payload = {
        "username": username,
        "password": new_password
    }
    
    logger.debug(f"Changing password payload: {payload}")
    try:
        response = requests.put(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Changing password failed with status code {response.status_code}: {response.text}")
            return False, response.json()
        
        logger.info("Password change successful.")
        return True, response.json()
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"Changing password failed: Unable to decode JSON response. {e}")
        return False, {}
    except requests.RequestException as e:
        logger.error(f"Changing password failed: {e}")
        return False, {}
    