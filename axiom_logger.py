import logging
import sys
from datetime import datetime

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"

class AxiomFormatter(logging.Formatter):
    """
    Custom formatter to handle specific color rules based on message content
    and 12-hour timestamps.
    """

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).strftime("%I:%M:%S%p")
        
        msg = record.getMessage()
        lower_msg = msg.lower()

        if record.levelno >= logging.ERROR or "error" in lower_msg or "exception" in lower_msg:
            color = RED
            icon = "✖"
        elif "contradiction" in lower_msg:
            color = BLUE
            icon = "‼"
        elif "uncorroborated" in lower_msg:
            color = MAGENTA
            icon = "?"
        elif "new fact" in lower_msg or "success" in lower_msg or "created" in lower_msg:
            color = CYAN
            icon = "✓"
        elif "initializing" in lower_msg or "starting" in lower_msg:
            color = YELLOW
            icon = "⟳"
        else:
            color = WHITE
            icon = "•"

        formatted_time = f"{DIM}{timestamp}{RESET}"
        formatted_msg = f"{color}{icon} {msg}{RESET}"
        
        return f"{formatted_time} {formatted_msg}"

def setup_logger():
    """Configures the root logger to use our custom formatter."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(AxiomFormatter())
    logger.addHandler(handler)
    
    logging.getLogger('werkzeug').setLevel(logging.ERROR)