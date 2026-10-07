"""Supervisor Verification and Evidence Gating endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import ServiceRequest, EvidenceItem, User
from app.core.deps import require_role
from app.services.workflow import transition
from app.services.evidence import calculate_evidence_completeness
from app.schemas.schemas import EvidenceReviewRequest
from app.core.time import utcnow

router = APIRouter(tags=["Verification Queue"])


@router.get("/verification/queue")
def get_verification_queue(
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """List all completed requests awaiting supervisor evidence verification."""
    reqs = (
        db.query(ServiceRequest)
        .filter(ServiceRequest.status == "COMPLETED")
        .order_by(ServiceRequest.completed_at.desc())
        .all()
    )
    results = []
    for r in reqs:
        completeness = calculate_evidence_completeness(db, r)
        results.append({
            "id": r.id,
            "code": r.code,
            "machine_code": r.machine.code,
            "machine_model": r.machine.model,
            "site_name": r.site.name,
            "fault_category": r.fault_category.name,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "completeness_score": completeness["score_percentage"],
            "missing_mandatory": completeness["missing_mandatory"],
            "is_ready_for_verification": completeness["is_complete"],
            "evidence_summary": completeness["summary"]
        })
    return results


@router.get("/requests/{id}/evidence")
def get_request_evidence(id: int, db: Session = Depends(get_db)):
    """Get full evidence checklist status and Proof of Presence results for a request."""
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")
    return calculate_evidence_completeness(db, req)


@router.post("/requests/{id}/verify")
def verify_request_completion(
    id: int,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Supervisor verifies completion.
    Domain Guard: Blocks verification if any mandatory evidence is missing or rejected.
    Transitions COMPLETED -> VERIFIED.
    Atomically issues reserved kit, deducts stock, and recalculates machine passport.
    """
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    completeness = calculate_evidence_completeness(db, req)
    if not completeness["is_complete"]:
        raise HTTPException(
            status_code=400,
            detail=f"Verification blocked: Missing mandatory items ({', '.join(completeness['missing_mandatory'])})"
        )

    transition(
        db=db,
        request=req,
        to_status="VERIFIED",
        actor_role=current_user.role,
        actor_id=current_user.id,
        actor_name=current_user.name,
        reason="Supervisor verified all mandatory evidence and accepted resolution."
    )

    return {
        "status": "VERIFIED",
        "verified_at": req.verified_at.isoformat(),
        "message": f"Service request {req.code} verified. Spare parts issued and machine passport updated."
    }


@router.post("/requests/{id}/evidence/{eid}/reject")
def reject_evidence_item(
    id: int,
    eid: int,
    data: EvidenceReviewRequest,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Reject an evidence item with feedback.
    Rejection Playbook: Returns job from COMPLETED to IN_PROGRESS so technician can resubmit.
    """
    ev = db.query(EvidenceItem).filter(EvidenceItem.id == eid, EvidenceItem.request_id == id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence item not found")

    ev.status = "REJECTED"
    ev.reviewer_note = data.reviewer_note or "Evidence rejected by supervisor; please re-upload clear photo."
    ev.reviewed_by = current_user.id
    ev.reviewed_at = utcnow()
    db.commit()

    req = ev.service_request
    if req.status == "COMPLETED":
        # Transition COMPLETED -> IN_PROGRESS
        transition(
            db=db,
            request=req,
            to_status="IN_PROGRESS",
            actor_role=current_user.role,
            actor_id=current_user.id,
            actor_name=current_user.name,
            reason=f"Evidence '{ev.template_key}' rejected: {ev.reviewer_note}"
        )

    return {
        "message": "Evidence item rejected. Request reverted to IN_PROGRESS for rectification.",
        "evidence_id": ev.id,
        "status": ev.status,
        "request_status": req.status
    }
