from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from app.core.logger import get_logger, setup_logging

setup_logging() 
logger = get_logger()

scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    job_defaults={"coalesce": True, "max_instances": 1},
)


def start_scheduler():
    """Start the APScheduler and register all cron jobs."""
    from app.crons.jobs import register_jobs
    logger.info("Schedule imported")
    register_jobs(scheduler)
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
