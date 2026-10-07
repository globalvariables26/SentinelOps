"""Exception Center, Hot-Swap, and What-If Rescue Simulator endpoints."""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import ExceptionFlag, ExceptionRule, User, ServiceRequest, Machine, Assignment, Site
from app.core.deps import require_role, get_current_user
from app.services.exceptions import get_what_if_options, execute_hotswap
from app.schemas.schemas import HotSwapRequest, ResolveExceptionRequest
from app.core.time import utcnow

router = APIRouter(prefix="/exceptions", tags=["Exceptions & Hot-Swap"])


@router.get("")
def list_exceptions(
    status: Optional[str] = "OPEN",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List exception flags with severity, root blocker, and options snapshot."""
    query = (db.query(ExceptionFlag)
        .join(ServiceRequest, ExceptionFlag.request_id == ServiceRequest.id)
        .join(Machine, ServiceRequest.machine_id == Machine.id)
        .join(Site, ServiceRequest.site_id == Site.id))
    if status:
        query = query.filter(ExceptionFlag.status == status)

    if current_user.role == "CUSTOMER" and current_user.customer_id:
        query = query.filter(Site.customer_id == current_user.customer_id)
    elif current_user.role == "TECHNICIAN" and current_user.technician_profile:
        query = query.join(Assignment, Assignment.request_id == ServiceRequest.id).filter(
            Assignment.technician_id == current_user.technician_profile.id,
            Assignment.status != "REPLACED",
        )
    elif current_user.role == "SUPERVISOR":
        query = query.filter(ExceptionFlag.owner_role == "SUPERVISOR")

    flags = query.order_by(ExceptionFlag.created_at.desc()).all()
    results = []
    for f in flags:
        req = f.service_request
        results.append({
            "id": f.id,
            "request_id": req.id,
            "request_code": req.code,
            "machine_code": req.machine.code,
            "site_name": req.site.name,
            "rule_code": f.rule_code,
            "severity": f.severity,
            "reason": f.reason,
            "blocker": f.blocker,
            "recommended_action": f.recommended_action,
            "owner_role": f.owner_role,
            "status": f.status,
            "options_snapshot": json.loads(f.options_snapshot) if f.options_snapshot else [],
            "resolution": f.resolution,
            "created_at": f.created_at.isoformat()
        })
    return results


@router.get("/{id}/options")
def get_rescue_options(id: int, db: Session = Depends(get_db)):
    """What-If Rescue Simulator:
    Fetches real-time computed recovery options A, B, C plus 'Wait for original technician',
    with ETAs, part sources, projected SLA outcomes, and cost buckets.
    """
    return get_what_if_options(db, id)


@router.post("/{id}/hotswap")
def hotswap_technician(
    id: int,
    data: HotSwapRequest,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Execute one-click Hot-Swap in an atomic transaction:
    Releases old reservations, replaces assignment, re-reserves parts,
    moves EXCEPTION -> ASSIGNED, notifies parties, and records tamper-evident audit.
    """
    req = execute_hotswap(
        db=db,
        exception_id=id,
        new_technician_id=data.technician_id,
        actor_id=current_user.id,
        actor_role=current_user.role,
        reason=data.reason or "Manager Hot-Swap executed"
    )
    return {
        "message": f"Hot-Swap successful! Request {req.code} reassigned and returned to ASSIGNED status.",
        "request_id": req.id,
        "request_code": req.code,
        "status": req.status
    }


@router.post("/{id}/resolve")
def resolve_exception(
    id: int,
    data: ResolveExceptionRequest,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Manually resolve an exception flag."""
    flag = db.query(ExceptionFlag).filter(ExceptionFlag.id == id).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Exception flag not found")

    flag.status = "RESOLVED"
    flag.resolution = data.resolution
    flag.resolved_at = utcnow()
    db.commit()

    return {"message": "Exception resolved", "exception_id": flag.id}
