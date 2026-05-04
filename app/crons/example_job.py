from datetime import datetime
from app.core.logger import get_logger

logger = get_logger()


async def health_check_job():
    """Example cron job that logs a health check message."""
    logger.info(f"[CronJob] Health check at {datetime.utcnow().isoformat()}")
