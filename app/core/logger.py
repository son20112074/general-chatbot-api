import os
import logging
from logging.handlers import RotatingFileHandler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "app.log")

logger = logging.getLogger("tms_api")

def setup_logging():
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    handler = RotatingFileHandler(LOG_FILE, maxBytes=10**6, backupCount=3)
    handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(handler)

    # aps_logger = logging.getLogger("apscheduler")
    # aps_logger.setLevel(level)
    # aps_logger.addHandler(handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    # aps_logger.addHandler(console_handler)


def get_logger():
    return logger