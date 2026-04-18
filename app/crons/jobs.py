from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.crons.example_job import health_check_job
from app.crons.graph_extraction_job import graph_extraction_job
from app.core.logger import get_logger

logger = get_logger()


def register_jobs(scheduler: AsyncIOScheduler):
    """
    Register all cron jobs here.
    Each job should be imported from its own module and added to the scheduler.
    """

    # Example: runs every 5 minutes
    scheduler.add_job(
        health_check_job,
        trigger="interval",
        minutes=5,
        id="health_check",
        name="Health Check",
        replace_existing=True,
    )

    # Graph extraction: process files every 30 seconds
    scheduler.add_job(
        graph_extraction_job,
        trigger="interval",
        seconds=30, # Run every 30 seconds
        id="graph_extraction",
        name="Graph Extraction",
        replace_existing=True,
    )

    logger.info(f"Registered {len(scheduler.get_jobs())} cron job(s)")
