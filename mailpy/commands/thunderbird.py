import argparse
import importlib.util
import os
import subprocess
import time

from typing import List, Optional

from mailpy.log import get_logger

logger = get_logger()

# Dependencies and DISPLAY check

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
        # Check if DISPLAY variable is set
        logger.debug("Checking DISPLAY environment variable...")
        if 'DISPLAY' not in os.environ:
            raise EnvironmentError("DISPLAY environment variable is not set. Please run this script in a graphical environment.")

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


def _focus_thunderbird_window():
    """Focus the Thunderbird window using wmctrl."""
    proc = subprocess.run(['wmctrl', '-lx'], capture_output=True, text=True)
    thunderbird_windows = [line for line in proc.stdout.splitlines() if 'Mail.thunderbird' in line]
    if thunderbird_windows:
        window_id = thunderbird_windows[0].split()[0]
        subprocess.run(['wmctrl', '-iR', window_id])
        logger.debug("Focused Thunderbird window with wmctrl")

        subprocess.run([
            "xdotool", "windowactivate", "--sync", window_id
        ])
        logger.debug("Focused Thunderbird window with xdotool")




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
    with LOCK_INPUT.acquire():
        logger.debug(f"Trying to acquire lock on {LOCK.lock_file}.")
        with LOCK.acquire():
            try:
                subprocess.Popen([thunderbird_path])
                logger.info("Thunderbird setup launched successfully.")
            except Exception as e:
                logger.error(f"Failed to setup Thunderbird: {e}")
                raise

            time.sleep(15)  # Min time to wait
            
            # # Try to kill and reopen it (avoid issues with new instances)
            # try:
            #     subprocess.Popen(["pkill", "thunderbird"])
            #     logger.info("Thunderbird killed successfully.")
            # except Exception as e:
            #     logger.error(f"Failed to killed Thunderbird: {e}")
            #     raise
            # time.sleep(5)  # Min time to wait

            # try:
            #     subprocess.Popen([thunderbird_path])
            #     logger.info("Thunderbird setup launched successfully.")
            # except Exception as e:
            #     logger.error(f"Failed to setup Thunderbird: {e}")
            #     raise
            # time.sleep(10)  # Min time to wait

            # Wait for Thunderbird to launch
            # max_retries = 10
            # retries = 0
            while not _check_thunderbird_running():  #  and retries < max_retries:
                logger.debug("Waiting for Thunderbird to launch...")
                # retries += 1
                time.sleep(1)

            # Use input-simulation to automate initial setup
            args = {
                # "--sleep": 1,
                # "--typing-interval": 0.0001  # 0.0
                # "--typing-interval": 0.5,
                "--press-interval": 0.1
            }
            # _focus_thunderbird_window()
            time.sleep(2)

            sequence = []

            add_account_sequence = [
                'K,Alt+A',
                'K,N',
                'K,E',
            ]
            sequence.extend(add_account_sequence)

            _input_keyboard_sequence(sequence, args)
            time.sleep(2)  # Wait for the Add Account window to open
            # _focus_thunderbird_window()

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
            time.sleep(5)  # Wait for potential certificate warning
            sequence = []

            proc = subprocess.run(['wmctrl', '-l'], capture_output=True, text=True)
            gedit_windows_after = [line for line in proc.stdout.splitlines() if 'excepción de seguridad' in line]
            if gedit_windows_after:
                logger.debug("Certificate warning window detected.")
                certificate_warning_sequence = [
                    'S,1',
                    'K,Tab,4',
                    'K,Space',
                ]
                sequence.extend(certificate_warning_sequence)

            finalize_sequence = [
                'S,3',
                'K,Tab,8',
                'K,Enter',
            ]
            sequence.extend(finalize_sequence)

            _input_keyboard_sequence(sequence, args)
            logger.info("Thunderbird setup completed.")
