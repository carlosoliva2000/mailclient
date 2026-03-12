import argparse
import importlib.util
import os
import subprocess
import time
import re

from typing import List, Optional

from mailpy.log import get_logger

logger = get_logger()


# Globals

CONTENTION_THRESHOLD = 0.5  # Seconds to consider that there is contention on the lock (i.e., that it was not acquired immediately)


# Input control

def get_user_input_device_ids():
    EXCLUDED_KEYWORDS = [
        "Virtual core",
        "XTEST",
        "Power Button",
        "Sleep Button",
        "Video Bus"
    ]
    
    result = subprocess.run(
        ["xinput", "list"],
        stdout=subprocess.PIPE,
        text=True
    )

    device_ids = []
    for line in result.stdout.splitlines():
        match = re.search(r'id=(\d+)', line)
        if not match:
            continue

        device_id = int(match.group(1))
        name = line.split("id=")[0].strip()

        if any(keyword in name for keyword in EXCLUDED_KEYWORDS):
            continue

        device_ids.append(device_id)
    
    logger.debug(f"Detected user input devices: {device_ids}")

    return device_ids


def _set_input_devices(enabled: bool):
    """
    Enable or disable user input devices using xinput.
    """
    # USER_INPUT_DEVICE_IDS = [9, 10, 11]
    
    action = "enable" if enabled else "disable"
    for dev_id in get_user_input_device_ids():
        try:
            res = subprocess.run(
                ["xinput", action, str(dev_id)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
            logger.debug(f"xinput {action} {dev_id}")
            if res.returncode != 0:
                logger.warning(f"xinput non-zero return code: {res.returncode}")
                logger.error(f"xinput error: {res.stderr}")
        except Exception as e:
            logger.error(f"Failed to {action} device {dev_id}: {e}")
    time.sleep(2)  # Fail-safe


def disable_user_input():
    logger.debug("Disabling user input devices.")
    _set_input_devices(False)


def enable_user_input():
    logger.debug("Enabling user input devices.")
    _set_input_devices(True)


# Dependencies and DISPLAY check

def _get_active_x11_session():
    """
    Returns (user, uid, runtime_path) if an active X11 session exists.
    Otherwise returns (None, None, None).
    """
    result = subprocess.run(
        ["loginctl", "--no-legend", "list-sessions"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return None, None, None

    for line in result.stdout.splitlines():
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        session, uid, user = parts[:3]

        info = subprocess.run(
            ["loginctl", "show-session", session],
            capture_output=True,
            text=True
        )

        data = {}
        for l in info.stdout.splitlines():
            if "=" in l:
                k, v = l.split("=", 1)
                data[k] = v

        if data.get("Active") == "yes" and data.get("Type") == "x11":

            runtime_info = subprocess.run(
                ["loginctl", "show-user", user, "-p", "RuntimePath"],
                capture_output=True,
                text=True
            )

            runtime_path = None
            if runtime_info.returncode == 0:
                line = runtime_info.stdout.strip()
                if "=" in line:
                    runtime_path = line.split("=", 1)[1]

            return user, uid, runtime_path

    return None, None, None


def _ensure_graphical_session(timeout=120):
    logger.info("Ensuring graphical session is ready...")

    start = time.perf_counter()

    while time.perf_counter() - start < timeout:
        user, uid, runtime_path = _get_active_x11_session()

        if not user:
            logger.debug("No active X11 session yet...")
            time.sleep(1)
            continue

        if not runtime_path:
            logger.debug("RuntimePath not available yet...")
            time.sleep(1)
            continue

        xauthority = os.path.join(runtime_path, "gdm", "Xauthority")

        if not os.path.exists(xauthority):
            logger.debug(f"Xauthority not found at {xauthority}")
            time.sleep(1)
            continue

        env = os.environ.copy()
        env["DISPLAY"] = ":0"
        env["XAUTHORITY"] = xauthority

        result = subprocess.run(
            ["xdpyinfo"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        if result.returncode == 0:
            logger.info(f"Graphical session ready for user {user}.")
            os.environ["DISPLAY"] = ":0"
            os.environ["XAUTHORITY"] = xauthority
            logger.info("Waiting an additional 1 second to ensure the session is fully ready...")
            time.sleep(1)
            return

        logger.debug("X server not accepting connections yet...")
        time.sleep(1)

    logger.error("Timeout waiting for graphical session.")
    exit(1)


def _check_binary(name: str) -> bool:
    """Check if a binary is installed."""
    res = subprocess.run(['which', name], capture_output=True, text=True)
    return res.returncode == 0


def _check_python_dependency(name: str) -> bool:
    """Check if a Python dependency is installed."""
    return importlib.util.find_spec(name) is not None


def _check_and_import_dependencies():
    """Check if all dependencies are installed and import them."""
    logger.debug("Checking dependencies...")
    try:
        # Check if dependencies are installed
        logger.debug("Checking required binaries and Python packages...")
        binaries = ['thunderbird', 'wmctrl', 'input-simulation']
        python_modules = ['filelock']

        bins_not_installed = []
        python_not_installed = []
        for bin in binaries:
            if not _check_binary(bin):
                bins_not_installed.append(bin)
        for py_mod in python_modules:
            if not _check_python_dependency(py_mod):
                python_not_installed.append(py_mod)
        
        if bins_not_installed or python_not_installed:
            error_msg = f"""
Some dependencies are not installed.
Binaries not installed: {bins_not_installed}.
Python packages not installed: {python_not_installed}.
Please install them and try again."""
            raise ModuleNotFoundError(error_msg)
            # raise ModuleNotFoundError(f"Dependencies not installed: {', '.join(not_installed)}. Please install them and try again.")

        # Everything is fine, import the dependencies
        logger.debug("All dependencies are installed.")

        global FileLock
        from filelock import FileLock

        # for mod in python_modules:
        #     globals()[mod] = importlib.import_module(mod)

        logger.debug("All dependencies imported.")
    except Exception as e:
        import traceback

        logger.error(f"Dependency check failed: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        logger.error(f"Environment variables: {os.environ}")
        exit(1)


# Lock setup

def _setup_locks():
    global LOCK, LOCK_INPUT
    LOCK = FileLock(os.path.join("/", "opt", "locks", ".mailpy.lock"))
    LOCK_INPUT = FileLock(os.path.join("/", "opt", "locks", ".input.lock"))


# Input simulation functions

def _set_env():
    """Set the INPUT_LOCK_HELD environment variable for subprocesses."""
    env = os.environ.copy()
    env['INPUT_LOCK_HELD'] = '1'  # Hint to input-simulation that the lock is already held
    return env


def _input_simulation(sequence: List[str], verb: str, args: Optional[dict] = None, debug: bool = False):
    """Simulate a sequence of inputs using input-simulation."""
    env = _set_env()

    # Convert args dict to a list of command line arguments
    args_l = [f"{key}={value}" if value else f"{key}" for key, value in args.items()] if args is not None else []
    if debug:
        args_l.append('--debug')
    sequence_string = ' '.join(sequence)

    if args_l:
        command = ['input-simulation', verb] + args_l + [f"{sequence_string}"]
    else:
        command = ['input-simulation', verb, f"{sequence_string}"]
    logger.debug(f"Invoking input-simulation command with verb '{verb}', args: {args_l} and sequence (truncated at 50): {sequence_string[:50]}...")
    subprocess.run(command, env=env)
    logger.debug("Returned from input-simulation.")


def _input_key(key: str, presses: int = 1, args: Optional[dict] = None, debug: bool = False):
    """Simulate a key press using input-simulation."""
    sequence = [f'K,{key},{presses}']
    _input_simulation(sequence, 'keyboard', args, debug)


def _input_type(text: str, args: Optional[dict] = None, debug: bool = False):
    """Simulate typing text using input-simulation."""
    sequence = [f'T,"{text}"']
    _input_simulation(sequence, 'keyboard', args, debug)


def _input_keyboard_sequence(sequence: List[str], args: Optional[dict] = None, debug: bool = False):
    """Simulate a sequence of keyboard actions using input-simulation."""
    _input_simulation(sequence, 'keyboard', args, debug)


def _input_sequence(sequence: List[str], args: Optional[dict] = None, debug: bool = False):
    """Simulate a sequence of inputs using input-simulation."""
    _input_simulation(sequence, 'input', args, debug)


def init():
    _ensure_graphical_session()
    _check_and_import_dependencies()
    _setup_locks()


def register_arguments(parser: argparse.ArgumentParser):
    """Register command-line arguments for thunderbird command."""
    parser.add_argument(
        "--thunderbird-path",
        type=str,
        required=False,
        default="thunderbird",
        help="Path to the Thunderbird executable. If not provided, assumes 'thunderbird' is in system PATH.",
    )
    parser.add_argument(
        "--name",
        type=str,
        required=False,
        help="Name shown to recipients. If not provided, defaults to account name.",
    )
    parser.add_argument(
        "--email",
        type=str,
        required=True,
        help="Email address of the account to set up Thunderbird for.",
    )
    parser.add_argument(
        "--password",
        type=str,
        required=False,
        help="Password for the email account. Not required if no authentication is needed.",
    )
    parser.add_argument(
        "--smtp-server",
        type=str,
        required=True,
        help="SMTP server address.",
    )
    parser.add_argument(
        "--smtp-port",
        type=int,
        default=465,
        help="SMTP server port.",
    )
    parser.add_argument(
        "--entry-server",
        type=str,
        required=False,
        help="Incoming mail server address (IMAP/POP3). If not provided, SMTP server will be used.",
    )
    parser.add_argument(
        "--entry-port",
        type=int,
        default=993,
        help="Incoming mail server port (IMAP/POP3).",
    )
    parser.add_argument(
        "--entry-security",
        type=str,
        choices=["SSL", "STARTTLS", "NONE"],
        default="SSL",
        help="Security type for incoming mail server.",
    )
    parser.add_argument(
        "--protocol",
        type=str,
        choices=["IMAP", "POP3"],
        default="IMAP",
        help="Protocol for incoming mail server.",
    )


def thunderbird_cli(args: argparse.Namespace):
    """Handle the thunderbird command."""
    setup_thunderbird(
        email=args.email,
        smtp_server=args.smtp_server,
        smtp_port=args.smtp_port,
        entry_server=args.entry_server,
        entry_port=args.entry_port,
        entry_security=args.entry_security,
        entry_protocol=args.protocol,
        name=args.name,
        password=args.password,
        thunderbird_path=args.thunderbird_path
    )


def _check_thunderbird_running() -> bool:
    """Check if Thunderbird is already running."""
    wmctrl_res = subprocess.run(['wmctrl', '-lx'], capture_output=True, text=True)
    thunderbird_windows = [line for line in wmctrl_res.stdout.splitlines() if 'Mail.thunderbird' in line]
    return len(thunderbird_windows) > 0


def _focus_thunderbird_window(security_exception: bool = False) -> bool:
    """Focus the Thunderbird window using wmctrl."""
    proc = subprocess.run(['wmctrl', '-lx'], capture_output=True, text=True)
    check_for = 'excepción de seguridad' if security_exception else 'Mail.thunderbird'
    thunderbird_windows = [line for line in proc.stdout.splitlines() if check_for in line]
    if thunderbird_windows:
        logger.debug(f"{'Certificate warning' if security_exception else 'Thunderbird'} window detected. Focusing it.")
        
        window_id = thunderbird_windows[0].split()[0]
        subprocess.run(['wmctrl', '-iR', window_id])
        logger.debug("Focused Thunderbird window with wmctrl.")

        subprocess.run([
            "xdotool", "windowactivate", "--sync", window_id
        ])
        logger.debug("Focused Thunderbird window with xdotool.")
        time.sleep(1)  # Give some time for the window to focus
    
    return bool(thunderbird_windows)


def setup_thunderbird(
    email: str,
    smtp_server: str,
    smtp_port: int = 465,
    entry_server: Optional[str] = None,
    entry_port: int = 993,
    entry_security: str = "SSL",
    entry_protocol: str = "IMAP",
    name: Optional[str] = None,
    password: Optional[str] = None,
    thunderbird_path: str = "thunderbird"
) -> None:
    """Setup Thunderbird email client."""
    logger.info(f"Setting up Thunderbird with path: {thunderbird_path}")
    init()

    # Check if Thunderbird is already running
    if _check_thunderbird_running():
        logger.info("Thunderbird is already running. Cannot proceed with setup.")
        return
    
    logger.debug(f"Trying to acquire input lock on {LOCK_INPUT.lock_file}.")
    start_t = time.perf_counter()
    with LOCK_INPUT.acquire():
        waited_t = time.perf_counter() - start_t
        if waited_t > CONTENTION_THRESHOLD:
            logger.debug(f"Input lock acquired after waiting {waited_t:.2f} seconds (contention detected).")
        else:
            logger.debug(f"Input lock acquired immediately (no contention).")
            
        disable_user_input()
        
        logger.debug(f"Trying to acquire lock on {LOCK.lock_file}.")
        start_t = time.perf_counter()
        with LOCK.acquire():
            waited_t = time.perf_counter() - start_t
            if waited_t > CONTENTION_THRESHOLD:
                logger.debug(f"Lock acquired after waiting {waited_t:.2f} seconds (contention detected).")
            else:
                logger.debug(f"Lock acquired immediately (no contention).")
            try:
                subprocess.Popen([thunderbird_path])
                logger.info("Thunderbird launched successfully.")
            except Exception as e:
                logger.error(f"Failed to launch Thunderbird: {e}")
                raise

            time.sleep(2)  # Min time to wait

            while not _check_thunderbird_running():  #  and retries < max_retries:
                logger.debug("Waiting for Thunderbird to launch...")
                # retries += 1
                time.sleep(1)

            # Use input-simulation to automate initial setup
            args = {
                "--sleep": 0.1,
                # "--typing-interval": 0.0001  # 0.0
                # "--typing-interval": 0.5,
                "--press-interval": 0.1,
            }
            time.sleep(1)
            _focus_thunderbird_window()

            sequence = []

            add_account_sequence = [
                'K,Alt+A',
                'K,N',
                'K,E',
            ]
            sequence.extend(add_account_sequence)

            _input_keyboard_sequence(sequence, args)
            time.sleep(2)  # Wait for the Add Account window to open
            _focus_thunderbird_window()

            sequence = []

            # Fill in email
            name = name if name else email.split('@')[0]
            fill_email_sequence = [
                f'T,"{name}"',
                'K,Tab',
                f'T,"{email}"',
                'K,Tab',
                f'T,"{password}"' if password else '',
                'K,Tab,3' if password else 'K,Tab,2',
                'K,Space',
                'K,Shift+Tab,13',
            ]
            sequence.extend(fill_email_sequence)

            # Entry server
            # Protocol selection
            protocol_sequence = [
                'K,Down,1',  # Select POP3
            ] if entry_protocol.upper() == "POP3" else []

            # Server name
            entry_server = entry_server if entry_server else smtp_server
            server_sequence = [
                'K,Tab',
                f'T,"{entry_server}"',
            ]

            # Security
            security_sequence = [
                'K,Tab,2',
                f'K,Down,{2 if entry_security == "SSL" else 1}',
            ] if entry_security != "NONE" else []

            # Port
            port_sequence = [
                'K,Shift+Tab',  # Go back to port field
                f'T,"{entry_port}"',
            ]

            # Authentication
            auth_sequence = [
                'K,Tab,2',
                'K,Down,1',  # Normal password
            ]

            sequence.extend(protocol_sequence)
            sequence.extend(server_sequence)
            sequence.extend(security_sequence)
            sequence.extend(port_sequence)
            sequence.extend(auth_sequence)

            # SMTP server
            # Server name
            server_sequence = [
                'K,Tab,2',
                f'T,"{smtp_server}"',
            ]

            # Security
            security_sequence = [
                'K,Tab,2',
                f'K,Down,{2 if entry_security == "SSL" else 1}',
            ] if entry_security != "NONE" else []
            
            # Port
            port_sequence = [
                'K,Shift+Tab',  # Go back to port field
                f'T,"{smtp_port}"',
            ]

            # Authentication
            auth_sequence = [
                'K,Tab,2',
                'K,Space',  # Show options
                'K,Down,2',  # Normal password
                'K,Enter',
            ]

            done_sequence = [
                'K,Tab,14',
                'K,Enter',  # Done
            ]

            sequence.extend(server_sequence)
            sequence.extend(security_sequence)
            sequence.extend(port_sequence)
            sequence.extend(auth_sequence)
            sequence.extend(done_sequence)
            _input_keyboard_sequence(sequence, args)


            # Check for certificate warning
            # time.sleep(2)  # Wait for potential certificate warning
            logger.info("Checking for certificate warning window...")
            is_certificate_window = False
            for _ in range(10):
                is_certificate_window = _focus_thunderbird_window(security_exception=True)
                if is_certificate_window:
                    break
                else:
                    logger.info("No certificate warning window detected yet, retrying...")
                    time.sleep(1)
            
            sequence = []

            if is_certificate_window:
                certificate_warning_sequence = [
                    # 'S,1',
                    'K,Alt+C',
                    # 'K,Tab,4',
                    # 'K,Space',
                ]
                sequence.extend(certificate_warning_sequence)

            finalize_sequence = [
                'S,3',
                'K,Tab,8',
                'K,Enter',
            ]
            sequence.extend(finalize_sequence)

            _input_keyboard_sequence(sequence, args)
            
            enable_user_input()
        logger.debug(f"Lock released on {LOCK.lock_file}.")
    logger.debug(f"Input lock released on {LOCK_INPUT.lock_file}.")
    logger.info("Thunderbird setup completed.")
