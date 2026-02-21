# axiom_logger.py
import logging
import sys
from datetime import datetime

# ANSI Color Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"         # For Contradictions
MAGENTA = "\033[95m"      # Pink - For Uncorroborated
CYAN = "\033[96m"         # Light Blue - For New Facts
WHITE = "\033[97m"

class AxiomFormatter(logging.Formatter):
    """
    Custom formatter to handle specific color rules based on message content
    and 12-hour timestamps.
    """

    def format(self, record):
        # 1. format the timestamp: 12:00:00AM
        # %I is 12h clock, %M min, %S sec, %p is AM/PM
        timestamp = datetime.fromtimestamp(record.created).strftime("%I:%M:%S%p")
        
        # 2. Determine color based on content keywords or Log Level
        msg = record.getMessage()
        lower_msg = msg.lower()

        if record.levelno >= logging.ERROR or "error" in lower_msg or "exception" in lower_msg:
            color = RED
            icon = "✖"
        elif "contradiction" in lower_msg:
            color = BLUE
            icon = "‼"
        elif "uncorroborated" in lower_msg:
            color = MAGENTA # Pink
            icon = "?"
        elif "new fact" in lower_msg or "success" in lower_msg or "created" in lower_msg:
            color = CYAN # Light Blue
            icon = "✓"
        elif "initializing" in lower_msg or "starting" in lower_msg:
            color = YELLOW
            icon = "⟳"
        else:
            color = WHITE
            icon = "•"

        # 3. Build the styled string
        # Format: [TIME] [ICON] MESSAGE
        # The timestamp gets the same color as the message, or we can make it DIM
        formatted_time = f"{DIM}{timestamp}{RESET}"
        formatted_msg = f"{color}{icon} {msg}{RESET}"
        
        return f"{formatted_time} {formatted_msg}"

def setup_logger():
    """Configures the root logger to use our custom formatter."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Prevent adding multiple handlers if function is called twice
    if logger.hasHandlers():
        logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(AxiomFormatter())
    logger.addHandler(handler)
    
    # Mute standard Flask/Workzeug generic logs slightly to keep console clean
    logging.getLogger('werkzeug').setLevel(logging.ERROR)