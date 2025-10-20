import os
import logging
import inspect

from logging.handlers import RotatingFileHandler
from typing import Optional


LOG_DIR = os.path.join(os.path.expanduser("~"), ".config", "mailclient")
LOG_PATH = os.path.join(LOG_DIR, "mailclient.log")
os.makedirs(LOG_DIR, exist_ok=True)


class LevelBasedFormatter(logging.Formatter):
    """Custom formatter that changes format based on log level."""
    def format(self, record):
        if record.levelno == logging.INFO:
            fmt = "%(message)s"
        else:
            fmt = "[%(levelname)s] %(message)s"
        return logging.Formatter(fmt).format(record)
    

def setup_global_logger(debug: bool = False):
    """Setup the global logger with file and console handlers.
    All modules use this configuration.
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    root_logger.setLevel(logging.DEBUG)

    # File handler
    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1024 * 1024, backupCount=3)
    file_formatter = logging.Formatter(
        "%(asctime)s [PID %(process)d] [%(name)s] [%(funcName)s] [%(levelname)s] %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    if debug:
        console_formatter = file_formatter  # Detailed format
        console_handler.setLevel(logging.DEBUG)
    else:
        console_formatter = LevelBasedFormatter()  # Simplified format
        console_handler.setLevel(logging.INFO)

    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger for the given module name.
    All loggers share the same configuration.
    """
    if name is None:
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        if module and module.__name__ != "__main__":
            name = module.__name__
        else:
            name = os.path.splitext(os.path.basename(frame.filename))[0]
    return logging.getLogger(name)


# def get_logger(name: Optional[str] = None, debug: bool = True) -> logging.Logger:
#     """Return a configured logger for the given module name."""
#     if name is None:
#         frame = inspect.stack()[1]
#         module = inspect.getmodule(frame[0])
#         if module and module.__name__ != "__main__":
#             name = module.__name__
#         else:
#             name = os.path.splitext(os.path.basename(frame.filename))[0]


#     logger = logging.getLogger(name)
#     if logger.handlers:
#         return logger  # Avoid duplicate handlers

#     logger.setLevel(logging.DEBUG)

#     file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1024*1024, backupCount=3)
#     console_handler = logging.StreamHandler()

#     formatter = logging.Formatter(
#         "%(asctime)s [PID %(process)d] [%(name)s] [%(funcName)s] [%(levelname)s] %(message)s"
#     )

#     file_handler.setFormatter(formatter)
#     console_handler.setFormatter(LevelBasedFormatter())
#     logger.addHandler(file_handler)
#     logger.addHandler(console_handler)

#     if debug:
#         console_handler.setFormatter(formatter)
#     else:
#         console_handler.setFormatter(LevelBasedFormatter())
#         console_handler.setLevel(logging.INFO)

#     logger.propagate = False

#     return logger
