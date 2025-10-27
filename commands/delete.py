import requests
import argparse

from typing import Dict, Tuple

from log import get_logger


logger = get_logger()

def register_arguments(parser: argparse.ArgumentParser):
    """Register command-line arguments for the delete command."""
    parser.add_argument(
        "username",
        type=str,
        # required=True,
        help="Username to delete.",
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


def delete_cli(args: argparse.Namespace):
    """Handle the delete command."""
    username = args.username
    server = args.server
    port = args.port

    delete_user(
        username=username,
        server=server,
        port=port
    )


def delete_user(
    username: str,
    server: str,
    port: int,
) -> Tuple[bool, Dict]:
    """Delete a user."""
    logger.info(f"Deleting user '{username}' on server '{server}:{port}'")

    # Send a DELETE request to /delete endpoint
    url = f"http://{server}:{port}/delete"
    payload = {
        "username": username
    }
    
    logger.debug(f"Delete user payload: {payload}")
    try:
        response = requests.delete(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Deleting user failed with status code {response.status_code}: {response.json()}")
            return False, response.json()
        
        logger.info("User deletion successful.")
        return True, response.json()
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"Deleting user failed: Unable to decode JSON response. {e}")
        return False, {}
    except requests.RequestException as e:
        logger.error(f"Deleting user failed: {e}")
        return False, {}
    