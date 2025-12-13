import os
import logging
from logging.handlers import RotatingFileHandler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "app.log")

logger = logging.getLogger("tms_api")

def setup_logging():
    logger.setLevel(LOG_LEVEL)

    handler = RotatingFileHandler(LOG_FILE, maxBytes=10**6, backupCount=3)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    logger.addHandler(handler)


def get_logger():
    return logger