"""Strict workflow lifecycle engine with role-gated transitions and guards.
THE ONLY place status changes in SentinelOps.
"""
from typing import Dict, Any, Optional, Set, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.db.models import ServiceRequest, Assignment, EvidenceItem, User
from app.services.audit import append_audit_log
from app.events.bus import emit
from app.core.time import utcnow


# Terminal statuses that cannot be transitioned out of
TERMINAL_STATUSES = {"VERIFIED", "REJECTED", "CANCELLED"}

# Allowed transitions map: (from_status, to_status) -> set of allowed actor roles
ALLOWED_TRANSITIONS: Dict[Tuple[str, str], Set[str]] = {
    ("CREATED", "VALIDATED"): {"SYSTEM", "ADMIN"},
    ("CREATED", "REJECTED"): {"SYSTEM", "ADMIN"},
    ("CREATED", "CANCELLED"): {"ADMIN", "MANAGER", "CUSTOMER"},

    ("VALIDATED", "PENDING_APPROVAL"): {"SYSTEM", "ADMIN"},
    ("VALIDATED", "ON_HOLD"): {"SYSTEM", "ADMIN"},
    ("VALIDATED", "CANCELLED"): {"ADMIN", "MANAGER", "CUSTOMER"},

    ("PENDING_APPROVAL", "APPROVED"): {"MANAGER", "ADMIN"},
    ("PENDING_APPROVAL", "REJECTED"): {"MANAGER", "ADMIN"},
    ("PENDING_APPROVAL", "ON_HOLD"): {"MANAGER", "ADMIN"},
    ("PENDING_APPROVAL", "CANCELLED"): {"ADMIN", "MANAGER", "CUSTOMER"},

    ("APPROVED", "ASSIGNED"): {"SYSTEM", "ADMIN", "MANAGER"},
    ("APPROVED", "CANCELLED"): {"ADMIN", "MANAGER"},

    ("ASSIGNED", "IN_PROGRESS"): {"TECHNICIAN", "ADMIN"},
    ("ASSIGNED", "EXCEPTION"): {"SYSTEM", "MANAGER", "ADMIN", "TECHNICIAN"},
    ("ASSIGNED", "CANCELLED"): {"ADMIN", "MANAGER"},

    ("IN_PROGRESS", "EXCEPTION"): {"SYSTEM", "TECHNICIAN", "MANAGER", "ADMIN"},
    ("IN_PROGRESS", "COMPLETED"): {"TECHNICIAN", "ADMIN"},
    ("IN_PROGRESS", "CANCELLED"): {"ADMIN", "MANAGER"},

    ("COMPLETED", "VERIFIED"): {"SUPERVISOR", "MANAGER", "ADMIN"},
    ("COMPLETED", "IN_PROGRESS"): {"SUPERVISOR", "MANAGER", "ADMIN"},
    ("COMPLETED", "CANCELLED"): {"ADMIN", "MANAGER"},

    ("EXCEPTION", "ASSIGNED"): {"MANAGER", "ADMIN", "SYSTEM"},
    ("EXCEPTION", "ON_HOLD"): {"MANAGER", "ADMIN"},
    ("EXCEPTION", "CANCELLED"): {"MANAGER", "ADMIN"},

    ("ON_HOLD", "VALIDATED"): {"MANAGER", "ADMIN"},
    ("ON_HOLD", "CANCELLED"): {"ADMIN", "MANAGER", "CUSTOMER"}
}


def check_guards(
    db: Session,
    request: ServiceRequest,
    to_status: str,
    actor_user: Optional[User],
    meta: Optional[Dict[str, Any]] = None
):
    """Enforce domain guards before allowing transition."""
    # Guard: ASSIGNED -> IN_PROGRESS: must have acknowledged, check-in, and safety confirmed
    if request.status == "ASSIGNED" and to_status == "IN_PROGRESS":
        active_assignment = (
            db.query(Assignment)
            .filter(Assignment.request_id == request.id, Assignment.status != "REPLACED")
            .order_by(Assignment.id.desc())
            .first()
        )
        if not active_assignment:
            raise HTTPException(status_code=400, detail="Cannot start: No active assignment found.")
        
        # If meta has safety_confirmed=True, update it
        if meta and meta.get("safety_confirmed"):
            request.safety_confirmed = True

        if not request.safety_confirmed:
            raise HTTPException(
                status_code=400,
                detail="Guard failed: Safety requirements and site permit must be explicitly confirmed."
            )

    # Guard: IN_PROGRESS -> COMPLETED: technician-side mandatory evidence must be submitted
    if request.status == "IN_PROGRESS" and to_status == "COMPLETED":
        # Check mandatory evidence templates for this fault category
        from app.db.models import EvidenceTemplateItem
        mandatory_templates = (
            db.query(EvidenceTemplateItem)
            .filter(
                EvidenceTemplateItem.fault_category_id == request.fault_category_id,
                EvidenceTemplateItem.mandatory == True,
                EvidenceTemplateItem.who_submits == "TECHNICIAN"
            )
            .all()
        )
        submitted_keys = {
            ev.template_key for ev in db.query(EvidenceItem)
            .filter(EvidenceItem.request_id == request.id)
            .all()
        }
        missing = [t.label for t in mandatory_templates if t.key not in submitted_keys]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Guard failed: Missing mandatory technician evidence: {', '.join(missing)}"
            )

    # Guard: COMPLETED -> VERIFIED: all mandatory evidence must be present and accepted
    if request.status == "COMPLETED" and to_status == "VERIFIED":
        from app.db.models import EvidenceTemplateItem
        mandatory_templates = (
            db.query(EvidenceTemplateItem)
            .filter(
                EvidenceTemplateItem.fault_category_id == request.fault_category_id,
                EvidenceTemplateItem.mandatory == True
            )
            .all()
        )
        evidence_items = (
            db.query(EvidenceItem)
            .filter(EvidenceItem.request_id == request.id)
            .all()
        )
        accepted_keys = {
            ev.template_key for ev in evidence_items
            if ev.status in ("ACCEPTED", "SUBMITTED")  # Technician evidence can be verified by supervisor
        }
        
        # Check if any item was rejected
        rejected_items = [ev for ev in evidence_items if ev.status == "REJECTED"]
        if rejected_items:
            raise HTTPException(
                status_code=400,
                detail=f"Guard failed: Request contains rejected evidence that must be re-submitted."
            )

        missing = [t.label for t in mandatory_templates if t.key not in accepted_keys]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Guard failed: Missing mandatory evidence items for verification: {', '.join(missing)}"
            )


def transition(
    db: Session,
    request: ServiceRequest,
    to_status: str,
    actor_role: str,
    actor_id: Optional[int] = None,
    actor_name: str = "System",
    reason: str = "",
    meta: Optional[Dict[str, Any]] = None
) -> ServiceRequest:
    """The central atomic state transition function.
    Validates lifecycle, verifies actor permissions, runs domain guards,
    applies timestamps, records audit log, and emits domain event.
    """
    from_status = request.status

    if from_status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from terminal status '{from_status}'."
        )

    # Validate transition path and role
    allowed_roles = ALLOWED_TRANSITIONS.get((from_status, to_status))
    if not allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition from '{from_status}' to '{to_status}'."
        )

    if actor_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{actor_role}' is not authorized to transition from '{from_status}' to '{to_status}'. Required: {allowed_roles}."
        )

    # Actor user lookup if provided
    actor_user = db.query(User).filter(User.id == actor_id).first() if actor_id else None

    # Run domain guards
    check_guards(db, request, to_status, actor_user, meta)

    # Snapshot before state
    before_state = {
        "status": from_status,
        "readiness_score": request.readiness_score,
        "risk_level": request.risk_level,
        "safety_confirmed": request.safety_confirmed
    }

    # Execute state change
    request.status = to_status
    now = utcnow()

    if to_status == "VALIDATED":
        request.validated_at = now
    elif to_status == "APPROVED":
        request.approved_at = now
    elif to_status == "ASSIGNED":
        request.assigned_at = now
    elif to_status == "IN_PROGRESS":
        request.started_at = now
    elif to_status == "COMPLETED":
        request.completed_at = now
    elif to_status == "VERIFIED":
        request.verified_at = now
    elif to_status == "ON_HOLD":
        request.hold_reason = reason

    # Snapshot after state
    after_state = {
        "status": to_status,
        "readiness_score": request.readiness_score,
        "risk_level": request.risk_level,
        "safety_confirmed": request.safety_confirmed,
        "reason": reason
    }

    db.commit()
    db.refresh(request)

    # Append to cryptographic hash chain
    append_audit_log(
        db=db,
        entity_type="ServiceRequest",
        entity_id=request.id,
        action=f"STATUS_TRANSITION_{from_status}_TO_{to_status}",
        actor_id=actor_id,
        actor_role=actor_role,
        before=before_state,
        after=after_state,
        meta={"reason": reason, **(meta or {})}
    )

    # Emit domain event
    event_payload = {
        "request_id": request.id,
        "request_code": request.code,
        "machine_id": request.machine_id,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
        "actor_role": actor_role,
        "meta": meta or {}
    }
    emit(f"request.status_changed", event_payload, actor=actor_name, db=db)
    emit(f"request.{to_status.lower()}", event_payload, actor=actor_name, db=db)

    return request
