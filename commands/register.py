import requests
import argparse

from typing import Optional, Dict, Tuple

from log import get_logger


logger = get_logger()

def register_arguments(parser: argparse.ArgumentParser):
    """Register command-line arguments for the register command."""
    parser.add_argument(
        "username",
        type=str,
        # required=True,
        help="Username for registration, e.g., email address.",
    )
    parser.add_argument(
        "password",
        type=str,
        # required=True,
        help="Password for registration.",
    )

    parser.add_argument(
        "--alias",
        type=str,
        help="Alias for the registered user.",
        default=None,
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


def register_user_cli(args: argparse.Namespace):
    """Handle the register command."""
    username = args.username
    password = args.password
    alias = args.alias
    server = args.server
    port = args.port

    register_user(
        username=username,
        password=password,
        server=server,
        port=port,
        alias=alias,
    )


def register_user(
    username: str,
    password: str,
    server: str,
    port: int,
    alias: Optional[str] = None,
) -> Tuple[bool, Dict]:
    """Register a user with the provided details."""
    logger.info(f"Registering user '{username}' with alias '{alias}' on server '{server}:{port}'")

    # Send a POST request to /register endpoint
    url = f"http://{server}:{port}/register"
    payload = {
        "username": username,
        "password": password,
    }
    if alias:
        payload["alias"] = alias
    
    logger.debug(f"Registration payload: {payload}")
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 201:
            logger.error(f"Registration failed with status code {response.status_code}: {response.json()}")
            return False, response.json()
        
        logger.info("Registration successful.")
        return True, response.json()
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"Registration failed: Unable to decode JSON response. {e}")
        return False, {}
    except requests.RequestException as e:
        logger.error(f"Registration failed: {e}")
        return False, {}
    