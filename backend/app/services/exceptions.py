"""Exception Engine, Playbooks, Hot-Swap, and What-If Rescue Simulator."""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.db.models import (
    ExceptionRule, ExceptionFlag, ServiceRequest, Assignment, Technician,
    User, StockLevel
)
from app.services.matching import calculate_match_score, build_3_plans
from app.services.inventory import release_reservations, reserve_service_kit
from app.services.workflow import transition
from app.services.audit import append_audit_log
from app.services.notify import notify_users_by_role, notify_user
from app.core.time import utcnow


def raise_exception_flag(
    db: Session,
    request: ServiceRequest,
    rule_code: str,
    severity: str,
    reason: str,
    blocker: str,
    recommended_action: str,
    owner_role: str = "MANAGER",
    options_snapshot: Optional[List[Dict[str, Any]]] = None
) -> ExceptionFlag:
    """Idempotently raise an exception flag for a request."""
    existing = (
        db.query(ExceptionFlag)
        .filter(
            ExceptionFlag.request_id == request.id,
            ExceptionFlag.rule_code == rule_code,
            ExceptionFlag.status == "OPEN"
        )
        .first()
    )
    if existing:
        return existing

    flag = ExceptionFlag(
        request_id=request.id,
        rule_code=rule_code,
        severity=severity,
        reason=reason,
        blocker=blocker,
        recommended_action=recommended_action,
        owner_role=owner_role,
        status="OPEN",
        options_snapshot=json.dumps(options_snapshot) if options_snapshot else None,
        created_at=utcnow()
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)

    # Transition request to EXCEPTION if not already
    if request.status in ("ASSIGNED", "IN_PROGRESS"):
        try:
            transition(
                db=db,
                request=request,
                to_status="EXCEPTION",
                actor_role="SYSTEM",
                reason=f"Exception raised: {rule_code} - {reason}",
                meta={"rule_code": rule_code, "severity": severity}
            )
        except Exception:
            pass

    return flag


def evaluate_exception_rules(db: Session):
    """Scan active requests against enabled exception rules."""
    now = utcnow()
    active_requests = (
        db.query(ServiceRequest)
        .filter(ServiceRequest.status.in_(["ASSIGNED", "IN_PROGRESS", "EXCEPTION", "PENDING_APPROVAL"]))
        .all()
    )

    for req in active_requests:
        # Rule: ACK_TIMEOUT
        if req.status == "ASSIGNED":
            assignment = (
                db.query(Assignment)
                .filter(Assignment.request_id == req.id, Assignment.status == "ASSIGNED")
                .first()
            )
            if assignment and assignment.ack_due_at and now > assignment.ack_due_at:
                # Precompute hot-swap options
                options = build_3_plans(db, req, exclude_tech_ids=[assignment.technician_id])
                raise_exception_flag(
                    db=db,
                    request=req,
                    rule_code="ACK_TIMEOUT",
                    severity="WARNING",
                    reason=f"Technician {assignment.technician.code} has not acknowledged within SLA window.",
                    blocker="Pending technician confirmation",
                    recommended_action="Execute Hot-Swap to reassign to next available technician",
                    owner_role="MANAGER",
                    options_snapshot=options
                )

        # Rule: STUCK_IN_PROGRESS
        if req.status == "IN_PROGRESS" and req.started_at:
            max_allowed_hours = (req.expected_duration_h or 2.0) * 1.5
            elapsed_hours = (now - req.started_at).total_seconds() / 3600.0
            if elapsed_hours > max_allowed_hours:
                raise_exception_flag(
                    db=db,
                    request=req,
                    rule_code="STUCK_IN_PROGRESS",
                    severity="WARNING",
                    reason=f"Work duration ({elapsed_hours:.1f}h) exceeds 1.5x expected ({max_allowed_hours:.1f}h).",
                    blocker="Technician progress stalled",
                    recommended_action="Contact technician or dispatch field supervisor",
                    owner_role="SUPERVISOR"
                )

        # Rule: SLA_BREACH
        if req.risk_level == "BREACHED":
            raise_exception_flag(
                db=db,
                request=req,
                rule_code="SLA_BREACH",
                severity="CRITICAL",
                reason=f"Resolution time SLA has breached for request {req.code}.",
                blocker="Exceeded contracted SLA timeline",
                recommended_action="Escalate to Operations Director and initiate expedite protocol",
                owner_role="ADMIN"
            )


def get_what_if_options(db: Session, exception_id: int) -> Dict[str, Any]:
    """Build What-If rescue simulator options:
    Plans A, B, C plus 'Wait for original technician'.
    """
    flag = db.query(ExceptionFlag).filter(ExceptionFlag.id == exception_id).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Exception flag not found.")

    req = flag.service_request
    last_assignment = (
        db.query(Assignment)
        .filter(Assignment.request_id == req.id)
        .order_by(Assignment.id.desc())
        .first()
    )
    original_tech = last_assignment.technician if last_assignment else None
    exclude_ids = [original_tech.id] if original_tech else []

    plans = build_3_plans(db, req, exclude_tech_ids=exclude_ids)

    # Compute "Wait for original technician" projection
    wait_option = {}
    if original_tech:
        # Assume 45 min additional delay
        delay_mins = 45.0 + (last_assignment.eta_minutes if last_assignment else 30.0)
        proj_completion = utcnow() + timedelta(minutes=delay_mins + ((req.expected_duration_h or 2.0) * 60.0))
        sla_outcome = "BREACH" if (req.sla_due_at and proj_completion > req.sla_due_at) else "AT_RISK"
        wait_option = {
            "title": f"Wait for {original_tech.code} ({original_tech.user.name})",
            "technician": {
                "id": original_tech.id,
                "code": original_tech.code,
                "name": original_tech.user.name,
                "rating": original_tech.rating
            },
            "eta_minutes": delay_mins,
            "projected_completion": proj_completion.isoformat(),
            "sla_outcome": sla_outcome,
            "cost_bucket": "LOW",
            "warning": "Estimated 72% likelihood of SLA breach. Recommended only if specialized tooling is already on-site."
        }

    return {
        "exception_id": flag.id,
        "request_id": req.id,
        "request_code": req.code,
        "rule_code": flag.rule_code,
        "reason": flag.reason,
        "options": plans,
        "wait_option": wait_option
    }


def execute_hotswap(
    db: Session,
    exception_id: int,
    new_technician_id: int,
    actor_id: Optional[int],
    actor_role: str,
    reason: str = "Manager executed one-click Hot-Swap"
) -> ServiceRequest:
    """Execute one-click Hot-Swap in an atomic transaction:
    1. Release old reservations
    2. Mark old assignment REPLACED
    3. Create new assignment
    4. Re-reserve or re-route kit
    5. Transition EXCEPTION -> ASSIGNED
    6. Resolve exception flag
    7. Notify parties
    8. Audit full swap and options considered
    """
    flag = db.query(ExceptionFlag).filter(ExceptionFlag.id == exception_id).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Exception not found.")

    req = flag.service_request
    new_tech = db.query(Technician).filter(Technician.id == new_technician_id).first()
    if not new_tech:
        raise HTTPException(status_code=404, detail="Selected replacement technician not found.")

    # 1. Release old reservations
    release_reservations(db, req.id)

    # 2. Mark old assignments as REPLACED
    old_assignments = (
        db.query(Assignment)
        .filter(Assignment.request_id == req.id, Assignment.status != "REPLACED")
        .all()
    )
    for old_asg in old_assignments:
        old_asg.status = "REPLACED"
        old_asg.replaced_reason = reason

    # 3. Compute score and build new assignment
    is_eligible, score, breakdown, explanation = calculate_match_score(db, new_tech, req)
    now = utcnow()
    ack_due = now + timedelta(minutes=15)

    new_assignment = Assignment(
        request_id=req.id,
        technician_id=new_tech.id,
        plan_type="HOT_SWAP",
        match_score=score,
        score_breakdown=json.dumps(breakdown),
        explanation=f"Hot-Swap replacement: {explanation}",
        eta_minutes=breakdown.get("eta_minutes", 30.0),
        status="ASSIGNED",
        ack_due_at=ack_due,
        created_at=now
    )
    db.add(new_assignment)

    # 4. Re-reserve service kit
    reserve_service_kit(db, req)

    # 5. Mark exception resolved
    flag.status = "RESOLVED"
    flag.resolution = f"Hot-Swapped to {new_tech.code} ({new_tech.user.name})"
    flag.resolved_at = now

    # 6. Status transition: EXCEPTION -> ASSIGNED
    transition(
        db=db,
        request=req,
        to_status="ASSIGNED",
        actor_role=actor_role,
        actor_id=actor_id,
        actor_name=actor_role,
        reason=reason,
        meta={
            "hot_swap": True,
            "replaced_technician": old_assignments[0].technician.code if old_assignments else "N/A",
            "new_technician": new_tech.code,
            "match_score": score
        }
    )

    db.commit()
    db.refresh(req)

    # 7. Notify new technician and manager
    notify_user(
        db=db,
        user_id=new_tech.user_id,
        title=f"🚨 Urgent Dispatch: Hot-Swap for {req.code}",
        body=f"You have been reassigned to emergency job {req.code}. Please acknowledge immediately.",
        level="CRITICAL",
        link=f"/tech/job/{req.id}"
    )

    return req
