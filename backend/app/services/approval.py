"""Manager and Dispatcher Approval API endpoints."""
import json
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import ServiceRequest, Assignment, Technician, User
from app.core.deps import require_role
from app.services.matching import build_3_plans
from app.services.inventory import reserve_service_kit
from app.services.workflow import transition
from app.services.validation import compute_readiness_gate
from app.schemas.schemas import ApproveRequest, RejectRequest, HoldRequest, CancelRequest
from app.core.time import utcnow

router = APIRouter(prefix="/requests", tags=["Approvals"])


@router.get("/{id}/plans")
def get_plans(id: int, db: Session = Depends(get_db)):
    """Fetch 3 explainable dispatch plans (Fastest, Best Fit, Least Disruptive) with breakdowns."""
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")
    return build_3_plans(db, req)


@router.post("/{id}/approve")
def approve_request(
    id: int,
    data: ApproveRequest,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Approve dispatch in one atomic transaction:
    1. Selects chosen plan (Fastest, Best Fit, Least Disruptive)
    2. Validates safety confirmation
    3. Moves PENDING_APPROVAL -> APPROVED -> ASSIGNED
    4. Reserves the service kit (parts, tools, consumables)
    5. Creates the Assignment record with ack_due_at deadline
    """
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    if not data.safety_confirmed:
        raise HTTPException(status_code=400, detail="Safety requirements must be confirmed prior to approval.")

    # 1. Fetch plans
    plans = build_3_plans(db, req)
    if not plans:
        raise HTTPException(status_code=400, detail="No eligible technicians available for dispatch.")

    # Select plan
    chosen_plan = next((p for p in plans if p["plan_type"] == data.plan_type), plans[0])
    tech_id = data.technician_id or chosen_plan["technician"]["id"]
    tech = db.query(Technician).filter(Technician.id == tech_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    req.safety_confirmed = True

    # 2. Atomic Transition: PENDING_APPROVAL -> APPROVED
    transition(
        db=db,
        request=req,
        to_status="APPROVED",
        actor_role=current_user.role,
        actor_id=current_user.id,
        actor_name=current_user.name,
        reason=f"Approved plan: {chosen_plan['plan_type']} assigned to {tech.code}",
        meta={"plan_type": chosen_plan["plan_type"], "technician": tech.code}
    )

    # 3. Reserve the Service Kit
    reservations = reserve_service_kit(db, req, plan_part_source=chosen_plan["part_source"])

    # 4. Create Assignment record
    now = utcnow()
    ack_due = now + timedelta(minutes=15)
    assignment = Assignment(
        request_id=req.id,
        technician_id=tech.id,
        plan_type=chosen_plan["plan_type"],
        match_score=chosen_plan["score"],
        score_breakdown=json.dumps(chosen_plan["breakdown"]),
        explanation=chosen_plan["explanation"],
        eta_minutes=chosen_plan["eta_minutes"],
        status="ASSIGNED",
        ack_due_at=ack_due,
        created_at=now
    )
    db.add(assignment)
    db.commit()

    # 5. Atomic Transition: APPROVED -> ASSIGNED
    transition(
        db=db,
        request=req,
        to_status="ASSIGNED",
        actor_role="SYSTEM",
        reason=f"Service kit reserved and assignment confirmed to {tech.code}",
        meta={"assignment_id": assignment.id, "technician_id": tech.id}
    )

    # 6. Recompute Readiness Score
    validation_data = json.loads(req.validation_report) if req.validation_report else {}
    readiness, passed, missing = compute_readiness_gate(db, req, validation_data)
    req.readiness_score = readiness
    db.commit()

    return {
        "status": "ASSIGNED",
        "message": f"Service request {req.code} approved and assigned to {tech.code} ({tech.user.name}).",
        "assignment_id": assignment.id,
        "readiness_score": req.readiness_score,
        "ack_due_at": ack_due.isoformat()
    }


@router.post("/{id}/reject")
def reject_request(
    id: int,
    data: RejectRequest,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Reject request from PENDING_APPROVAL."""
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    transition(
        db=db,
        request=req,
        to_status="REJECTED",
        actor_role=current_user.role,
        actor_id=current_user.id,
        actor_name=current_user.name,
        reason=data.reason
    )
    return {"status": "REJECTED", "message": f"Service request {req.code} rejected: {data.reason}"}


@router.post("/{id}/hold")
def hold_request(
    id: int,
    data: HoldRequest,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Place request ON_HOLD."""
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    transition(
        db=db,
        request=req,
        to_status="ON_HOLD",
        actor_role=current_user.role,
        actor_id=current_user.id,
        actor_name=current_user.name,
        reason=data.reason
    )
    return {"status": "ON_HOLD", "message": f"Service request {req.code} placed on hold: {data.reason}"}


@router.post("/{id}/cancel")
def cancel_request(
    id: int,
    data: CancelRequest,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER", "CUSTOMER"])),
    db: Session = Depends(get_db)
):
    """Cancel request and release any reserved inventory."""
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    from app.services.inventory import release_reservations
    release_reservations(db, req.id)

    transition(
        db=db,
        request=req,
        to_status="CANCELLED",
        actor_role=current_user.role,
        actor_id=current_user.id,
        actor_name=current_user.name,
        reason=data.reason
    )
    return {"status": "CANCELLED", "message": f"Service request {req.code} cancelled."}
