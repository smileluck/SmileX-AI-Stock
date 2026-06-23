import json
import logging
import time
from datetime import datetime
from functools import wraps

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=4)},
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 3600,
    },
)

SLOW_JOB_THRESHOLD_SECONDS = 30.0


def _log_job_failure(job_id: str, duration: float, error: str) -> None:
    try:
        from app.database import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    job_id,
                    "scheduler",
                    json.dumps({"error": error[:500]}, ensure_ascii=False),
                    0,
                    "error",
                    duration,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("write sync_log failed for job %s", job_id)


def _wrap(func, job_id: str):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            duration = time.perf_counter() - start
            if duration >= SLOW_JOB_THRESHOLD_SECONDS:
                logger.warning("job %s done in %.1fs (slow)", job_id, duration)
            else:
                logger.info("job %s done in %.1fs", job_id, duration)
            return result
        except Exception as e:
            duration = time.perf_counter() - start
            logger.exception("job %s failed after %.1fs", job_id, duration)
            _log_job_failure(job_id, duration, repr(e))
            raise
    return wrapper


def add_job(func, job_id: str, seconds: int = 300, replace: bool = True, cron: str | None = None):
    if cron:
        parts = cron.split()
        trigger = CronTrigger(minute=parts[0], hour=parts[1], day=parts[2], month=parts[3], day_of_week=parts[4])
    else:
        trigger = IntervalTrigger(seconds=seconds)
    scheduler.add_job(_wrap(func, job_id), trigger=trigger, id=job_id, replace_existing=replace)


def remove_job(job_id: str):
    scheduler.remove_job(job_id)


def get_jobs():
    return [
        {
            "id": job.id,
            "next_run": str(job.next_run_time),
            "trigger": str(job.trigger),
        }
        for job in scheduler.get_jobs()
    ]


def start_scheduler():
    if not scheduler.running:
        scheduler.start()


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
