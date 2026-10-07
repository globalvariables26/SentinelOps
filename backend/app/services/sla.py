"""Predictive SLA Risk Engine and Escalation Ladder."""
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.db.models import ServiceRequest, Assignment, Reservation, AuditLog
from app.services.notify import notify_users_by_role
from app.services.audit import append_audit_log
from app.core.time import utcnow


def calculate_sla_risk(
    db: Session,
    request: ServiceRequest
) -> Tuple[float, str]:
    """Calculate predictive risk_ratio and risk_level (SAFE, AT_RISK, CRITICAL, BREACHED)."""
    if request.status in ("COMPLETED", "VERIFIED", "REJECTED", "CANCELLED"):
        return 0.0, "SAFE"

    if not request.sla_due_at:
        return 0.0, "SAFE"

    now = utcnow()
    created_at = request.created_at
    total_sla_seconds = max(1.0, (request.sla_due_at - created_at).total_seconds())
    elapsed_seconds = (now - created_at).total_seconds()

    # If already past deadline
    if now >= request.sla_due_at:
        return 1.1, "BREACHED"

    expected_duration_seconds = (request.expected_duration_h or 2.0) * 3600.0
    active_assignment = (
        db.query(Assignment)
        .filter(Assignment.request_id == request.id, Assignment.status != "REPLACED")
        .order_by(Assignment.id.desc())
        .first()
    )

    remaining_seconds = expected_duration_seconds

    if request.status == "ASSIGNED":
        travel_sec = (active_assignment.eta_minutes * 60.0) if active_assignment else 1800.0
        
        # Check if parts are in transit
        part_transit = (
            db.query(Reservation)
            .filter(Reservation.request_id == request.id, Reservation.status == "IN_TRANSIT")
            .first()
        )
        part_transit_sec = 0.0
        if part_transit and part_transit.eta and part_transit.eta > now:
            part_transit_sec = (part_transit.eta - now).total_seconds()

        remaining_seconds = max(travel_sec, part_transit_sec) + expected_duration_seconds

        # Penalty if unacknowledged past ack_due_at
        if active_assignment and active_assignment.status == "ASSIGNED" and active_assignment.ack_due_at:
            if now > active_assignment.ack_due_at:
                penalty_sec = (now - active_assignment.ack_due_at).total_seconds() * 1.5
                remaining_seconds += penalty_sec

    elif request.status == "IN_PROGRESS":
        started_at = request.started_at or now
        worked_seconds = max(0.0, (now - started_at).total_seconds())
        remaining_seconds = max(0.0, expected_duration_seconds - worked_seconds)

    # Risk Ratio formula: (elapsed + remaining_estimate) / total_SLA
    risk_ratio = round((elapsed_seconds + remaining_seconds) / total_sla_seconds, 2)

    if risk_ratio < 0.70:
        level = "SAFE"
    elif risk_ratio < 0.90:
        level = "AT_RISK"
    elif risk_ratio <= 1.00:
        level = "CRITICAL"
    else:
        level = "BREACHED"

    return risk_ratio, level


def evaluate_sla_escalation(db: Session, request: ServiceRequest, old_level: str, new_level: str):
    """Trigger escalating notifications when risk level increases."""
    if old_level == new_level:
        return

    req_code = request.code

    if new_level == "AT_RISK":
        notify_users_by_role(
            db=db,
            roles=["MANAGER", "ADMIN"],
            title=f"⚠️ SLA At Risk: {req_code}",
            body=f"Service request {req_code} projected completion is entering yellow window (Risk ratio: {request.risk_ratio}).",
            level="WARNING",
            link=f"/requests/{request.id}"
        )
    elif new_level == "CRITICAL":
        notify_users_by_role(
            db=db,
            roles=["SUPERVISOR", "MANAGER", "ADMIN"],
            title=f"🚨 CRITICAL SLA Risk: {req_code}",
            body=f"Service request {req_code} is near breach ({int(request.risk_ratio * 100)}% SLA consumed). Expedite resolution.",
            level="CRITICAL",
            link=f"/requests/{request.id}"
        )
    elif new_level == "BREACHED":
        notify_users_by_role(
            db=db,
            roles=["ADMIN", "MANAGER"],
            title=f"⛔ SLA BREACHED: {req_code}",
            body=f"Service request {req_code} has officially breached target resolution time.",
            level="CRITICAL",
            link=f"/requests/{request.id}"
        )
        append_audit_log(
            db=db,
            entity_type="ServiceRequest",
            entity_id=request.id,
            action="SLA_BREACH_RECORDED",
            actor_id=None,
            actor_role="SYSTEM",
            before={"risk_level": old_level},
            after={"risk_level": "BREACHED", "risk_ratio": request.risk_ratio},
            meta={"note": "Automated SLA breach registered by SLA risk monitor"}
        )
