from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BackgroundScheduler()


def add_job(func, job_id: str, seconds: int = 300, replace: bool = True):
    scheduler.add_job(func, trigger=IntervalTrigger(seconds=seconds), id=job_id, replace_existing=replace)


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
