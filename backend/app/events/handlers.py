"""Domain Event Subscribers and Reactivity Handlers."""
import asyncio
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.events.bus import subscribe
from app.services.notify import notify_users_by_role, notify_user
from app.api.ws import ws_manager
from app.db.models import ServiceRequest, Assignment, Technician

logger = logging.getLogger("sentinelops.event_handlers")


def handle_request_events(event_type: str, payload: Dict[str, Any], db: Session):
    """Handle status changes and lifecycle events."""
    request_id = payload.get("request_id")
    request_code = payload.get("request_code")
    to_status = payload.get("to_status")
    from_status = payload.get("from_status")

    # 1. Real-time WebSocket Broadcast
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(
                ws_manager.broadcast({
                    "type": "request_updated",
                    "request_id": request_id,
                    "code": request_code,
                    "status": to_status
                })
            )
        else:
            asyncio.run(
                ws_manager.broadcast({
                    "type": "request_updated",
                    "request_id": request_id,
                    "code": request_code,
                    "status": to_status
                })
            )
    except Exception as e:
        logger.debug(f"Async broadcast dispatch: {e}")

    # 2. Role-specific notifications
    if to_status == "PENDING_APPROVAL":
        notify_users_by_role(
            db=db,
            roles=["MANAGER", "ADMIN"],
            title=f"Request {request_code} Needs Approval",
            body=f"Request {request_code} passed auto-validation and is awaiting dispatch approval.",
            level="INFO",
            link=f"/requests/{request_id}"
        )
    elif to_status == "ASSIGNED":
        # Notify the assigned technician
        assignment = (
            db.query(Assignment)
            .filter(Assignment.request_id == request_id, Assignment.status != "REPLACED")
            .order_by(Assignment.id.desc())
            .first()
        )
        if assignment:
            tech = db.query(Technician).filter(Technician.id == assignment.technician_id).first()
            if tech and tech.user_id:
                notify_user(
                    db=db,
                    user_id=tech.user_id,
                    title=f"New Job Assigned: {request_code}",
                    body=f"You have been assigned to service request {request_code}. Please acknowledge promptly.",
                    level="INFO",
                    link=f"/tech/job/{request_id}"
                )
    elif to_status == "EXCEPTION":
        notify_users_by_role(
            db=db,
            roles=["MANAGER", "ADMIN"],
            title=f"EXCEPTION: Request {request_code}",
            body=f"Service request {request_code} encountered an exception. Immediate review required.",
            level="CRITICAL",
            link=f"/exceptions"
        )
    elif to_status == "COMPLETED":
        notify_users_by_role(
            db=db,
            roles=["SUPERVISOR", "MANAGER"],
            title=f"Job Completed: {request_code}",
            body=f"Technician completed {request_code}. Ready for evidence verification.",
            level="INFO",
            link=f"/verification"
        )
    elif to_status == "VERIFIED":
        # Deduct inventory items and recompute machine passport
        from app.services.inventory import issue_reserved_kit
        from app.services.passport import recalculate_machine_passport, check_repeat_failure_loop
        
        issue_reserved_kit(db, request_id)
        
        req = db.query(ServiceRequest).filter(ServiceRequest.id == request_id).first()
        if req:
            recalculate_machine_passport(db, req.machine_id)
            check_repeat_failure_loop(db, req.machine_id, req.fault_category_id)


def register_event_handlers():
    """Register all domain subscribers."""
    subscribe("request.status_changed", handle_request_events)
