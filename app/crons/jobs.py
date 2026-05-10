from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.crons.example_job import health_check_job
from app.crons.graph_extraction_job import graph_extraction_job
from app.crons.topic_classification_job import topic_classification_job
from app.core.config import settings
from app.crons.report_export_job import (
    report_export_daily_job,
    report_export_weekly_job,
    report_export_monthly_job,
    report_export_quarterly_job,
)
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
    # scheduler.add_job(
    #     graph_extraction_job,
    #     trigger="interval",
    #     seconds=30,
    #     id="graph_extraction",
    #     name="Graph Extraction",
    #     replace_existing=True,
    # )

    # Topic classification: classify files every 30 seconds
    # scheduler.add_job(
    #     topic_classification_job,
    #     trigger="interval",
    #     seconds=settings.TOPIC_CLASSIFY_INTERVAL_SECONDS,
    #     id="topic_classification",
    #     name="Topic Classification",
    #     replace_existing=True,
    #     max_instances=1,
    # )
    scheduler.add_job(
        report_export_daily_job,
        trigger="cron",
        hour=2,
        minute=0,
        id="report_export_daily",
        name="Report Export (Daily)",
        replace_existing=True,
    )

    scheduler.add_job(
        report_export_weekly_job,
        trigger="cron",
        hour=22,
        minute=0,
        id="report_export_weekly",
        name="Report Export (Weekly)",
        replace_existing=True,
    )

    scheduler.add_job(
        report_export_monthly_job,
        trigger="cron",
        hour=22,
        minute=0,
        id="report_export_monthly",
        name="Report Export (Monthly)",
        replace_existing=True,
    )

    scheduler.add_job(
        report_export_quarterly_job,
        trigger="cron",
        hour=22,
        minute=0,
        id="report_export_quarterly",
        name="Report Export (Quarterly)",
        replace_existing=True,
    )

    # # One-shot test: run weekly extraction with last-3-months files, 5 s after startup
    # scheduler.add_job(
    #     test_report_export_weekly,
    #     trigger="date",
    #     run_date=datetime.now() + timedelta(seconds=5),
    #     id="test_report_export_weekly",
    #     name="Test Report Export (Weekly – Last 3 Months)",
    #     replace_existing=True,
    # )

    logger.info(f"Registered {len(scheduler.get_jobs())} cron job(s)")
