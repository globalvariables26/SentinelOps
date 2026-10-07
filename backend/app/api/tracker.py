"""Public Unauthenticated Live Tracker for Customers."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import ServiceRequest, Assignment

router = APIRouter(tags=["Public Customer Tracker"])


@router.get("/track/{token}")
def get_public_tracker(token: str, db: Session = Depends(get_db)):
    """Unauthenticated read-only endpoint for live customer progress tracking."""
    req = db.query(ServiceRequest).filter(ServiceRequest.track_token == token).first()
    if not req:
        raise HTTPException(status_code=404, detail="Tracking token not found or expired.")

    active_asg = (
        db.query(Assignment)
        .filter(Assignment.request_id == req.id, Assignment.status != "REPLACED")
        .order_by(Assignment.id.desc())
        .first()
    )

    tech_first_name = active_asg.technician.user.name.split()[0] if active_asg else "Assigned Specialist"
    eta_mins = active_asg.eta_minutes if active_asg else None

    # Simplified customer-safe timeline
    timeline = []
    if req.created_at:
        timeline.append({"step": "Request Created", "time": req.created_at.isoformat(), "completed": True})
    if req.validated_at:
        timeline.append({"step": "Automated Validation", "time": req.validated_at.isoformat(), "completed": True})
    if req.approved_at:
        timeline.append({"step": "Dispatch Approved", "time": req.approved_at.isoformat(), "completed": True})
    if req.assigned_at:
        timeline.append({"step": f"Technician En Route ({tech_first_name})", "time": req.assigned_at.isoformat(), "completed": True})
    if req.started_at:
        timeline.append({"step": "Work In Progress", "time": req.started_at.isoformat(), "completed": True})
    if req.completed_at:
        timeline.append({"step": "Repair Completed", "time": req.completed_at.isoformat(), "completed": True})
    if req.verified_at:
        timeline.append({"step": "Quality Verified & Closed", "time": req.verified_at.isoformat(), "completed": True})

    return {
        "request_code": req.code,
        "machine_code": req.machine.code,
        "machine_model": req.machine.model,
        "site_name": req.site.name,
        "status": req.status,
        "technician_first_name": tech_first_name,
        "eta_minutes": eta_mins,
        "timeline": timeline
    }
