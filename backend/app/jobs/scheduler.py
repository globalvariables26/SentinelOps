"""Background job scheduler running every 30 seconds for SLA recompute and exception scanning."""
import logging
try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    class BackgroundScheduler:
        def __init__(self): self.running=False
        def add_job(self, *args, **kwargs): pass
        def start(self): self.running=True
        def shutdown(self, wait=False): self.running=False

from app.db.session import SessionLocal
from app.services.sla import calculate_sla_risk, evaluate_sla_escalation
from app.services.exceptions import evaluate_exception_rules
from app.db.models import ServiceRequest

logger = logging.getLogger("sentinelops.scheduler")
scheduler = BackgroundScheduler()


def run_scheduled_checks():
    """Periodic job executed every 30 seconds."""
    db = SessionLocal()
    try:
        # 1. SLA Risk recompute for all active jobs
        active_reqs = (
            db.query(ServiceRequest)
            .filter(ServiceRequest.status.in_(["ASSIGNED", "IN_PROGRESS", "EXCEPTION", "PENDING_APPROVAL"]))
            .all()
        )
        for req in active_reqs:
            old_level = req.risk_level
            ratio, level = calculate_sla_risk(db, req)
            req.risk_ratio = ratio
            req.risk_level = level
            evaluate_sla_escalation(db, req, old_level, level)

        db.commit()

        # 2. Exception engine scan
        evaluate_exception_rules(db)

    except Exception as e:
        logger.error(f"Scheduler check cycle error: {e}")
    finally:
        db.close()


def start_scheduler():
    """Start APScheduler background scheduler."""
    if not scheduler.running:
        scheduler.add_job(
            run_scheduled_checks,
            "interval",
            seconds=30,
            id="sentinel_risk_and_exceptions",
            replace_existing=True
        )
        scheduler.start()
        logger.info("APScheduler background scheduler started (30s tick).")


def shutdown_scheduler():
    """Stop APScheduler background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler background scheduler stopped.")
