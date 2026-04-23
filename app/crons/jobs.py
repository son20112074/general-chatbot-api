from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.crons.example_job import health_check_job
from app.crons.graph_extraction_job import graph_extraction_job
from app.crons.topic_classification_job import topic_classification_job
from app.core.config import settings
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

    # Topic classification: classify files every 30 seconds
    scheduler.add_job(
        topic_classification_job,
        trigger="interval",
        seconds=settings.TOPIC_CLASSIFY_INTERVAL_SECONDS,
        id="topic_classification",
        name="Topic Classification",
        replace_existing=True,
        max_instances=1,
    )

    logger.info(f"Registered {len(scheduler.get_jobs())} cron job(s)")
