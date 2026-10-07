"""Technician Field Workspace and Assignment lifecycle endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import (
    Technician, Assignment, ServiceRequest, TaskLog, EvidenceItem,
    EvidenceTemplateItem, User
)
from app.core.deps import get_current_user, require_role
from app.services.workflow import transition
from app.services.evidence import check_proof_of_presence, calculate_evidence_completeness
from app.services.exceptions import raise_exception_flag
from app.services.matching import build_3_plans
from app.plugins.storage import save_upload_file
from app.schemas.schemas import CheckinRequest, StartWorkRequest, TaskLogCreate
from app.core.time import utcnow

router = APIRouter(tags=["Technicians & Assignments"])


# --- Technician Profiles & Status ---

@router.get("/technicians")
def list_technicians(db: Session = Depends(get_db)):
    """List field technicians with skills, rating, live status, and workload."""
    techs = db.query(Technician).all()
    results = []
    for t in techs:
        skills_summary = [f"{ts.skill.name} (Lvl {ts.level})" for ts in t.skills]
        certs = [c.machine_model for c in t.certifications]
        results.append({
            "id": t.id,
            "code": t.code,
            "name": t.user.name,
            "email": t.user.email,
            "status": t.status,
            "rating": t.rating,
            "hourly_rate": t.hourly_rate,
            "max_daily_jobs": t.max_daily_jobs,
            "current_location": {"lat": t.current_lat, "lng": t.current_lng},
            "skills": skills_summary,
            "certifications": certs,
            "last_checkin": t.last_checkin.isoformat() if t.last_checkin else None
        })
    return results


@router.patch("/technicians/{id}/status")
def update_technician_status(
    id: int,
    status: str,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER", "TECHNICIAN"])),
    db: Session = Depends(get_db)
):
    """Update technician duty status (AVAILABLE, BUSY, OFF_DUTY, UNAVAILABLE)."""
    tech = db.query(Technician).filter(Technician.id == id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    tech.status = status.upper()
    db.commit()
    return {"id": tech.id, "code": tech.code, "status": tech.status}


# --- Assignment Lifecycle (Ack, Decline, Check-in, Start, Complete) ---

@router.post("/assignments/{id}/acknowledge")
def acknowledge_assignment(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Technician acknowledges dispatch assignment within ack window."""
    asg = db.query(Assignment).filter(Assignment.id == id).first()
    if not asg:
        raise HTTPException(status_code=404, detail="Assignment not found")

    asg.status = "ACKNOWLEDGED"
    asg.acknowledged_at = utcnow()
    db.commit()

    # Update readiness score
    from app.services.validation import compute_readiness_gate
    import json
    val_data = json.loads(asg.service_request.validation_report) if asg.service_request.validation_report else {}
    score, passed, missing = compute_readiness_gate(db, asg.service_request, val_data)
    asg.service_request.readiness_score = score
    db.commit()

    return {"status": "ACKNOWLEDGED", "acknowledged_at": asg.acknowledged_at.isoformat()}


@router.post("/assignments/{id}/decline")
def decline_assignment(
    id: int,
    reason: str = "Technician declined assignment",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Technician declines assignment. Triggers TECH_DECLINE exception and prepares Hot-Swap."""
    asg = db.query(Assignment).filter(Assignment.id == id).first()
    if not asg:
        raise HTTPException(status_code=404, detail="Assignment not found")

    asg.status = "DECLINED"
    asg.replaced_reason = reason
    db.commit()

    req = asg.service_request

    # Compute top 3 replacements excluding declining tech
    replacement_options = build_3_plans(db, req, exclude_tech_ids=[asg.technician_id])

    # Raise exception flag
    flag = raise_exception_flag(
        db=db,
        request=req,
        rule_code="TECH_DECLINE",
        severity="WARNING",
        reason=f"Technician {asg.technician.code} ({asg.technician.user.name}) declined: {reason}",
        blocker="Assigned technician declined dispatch",
        recommended_action="Execute Hot-Swap to reassign immediately to recommended candidate.",
        owner_role="MANAGER",
        options_snapshot=replacement_options
    )

    return {
        "status": "DECLINED",
        "exception_id": flag.id,
        "message": "Assignment declined. Exception flag created and hot-swap candidates generated."
    }


@router.post("/assignments/{id}/checkin")
def checkin_at_site(
    id: int,
    data: CheckinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Technician records physical arrival at site with GPS coordinates."""
    asg = db.query(Assignment).filter(Assignment.id == id).first()
    if not asg:
        raise HTTPException(status_code=404, detail="Assignment not found")

    tech = asg.technician
    tech.current_lat = data.lat
    tech.current_lng = data.lng
    tech.last_checkin = utcnow()

    # Proof of Presence verification
    presence_status, dist_m = check_proof_of_presence(asg.service_request.site, data.lat, data.lng)
    db.commit()

    return {
        "message": "Check-in recorded successfully.",
        "presence_status": presence_status,
        "distance_meters": dist_m,
        "checkin_time": tech.last_checkin.isoformat()
    }


@router.post("/assignments/{id}/start")
def start_work(
    id: int,
    data: StartWorkRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Technician confirms site safety requirements and starts work (ASSIGNED -> IN_PROGRESS)."""
    asg = db.query(Assignment).filter(Assignment.id == id).first()
    if not asg:
        raise HTTPException(status_code=404, detail="Assignment not found")

    req = asg.service_request
    asg.status = "IN_PROGRESS"

    # Transition ServiceRequest: ASSIGNED -> IN_PROGRESS
    transition(
        db=db,
        request=req,
        to_status="IN_PROGRESS",
        actor_role="TECHNICIAN",
        actor_id=current_user.id,
        actor_name=current_user.name,
        reason="Technician confirmed safety permits and commenced repair work.",
        meta={"safety_confirmed": data.safety_confirmed}
    )

    return {"status": "IN_PROGRESS", "started_at": req.started_at.isoformat()}


@router.post("/requests/{id}/tasks")
def log_task(
    id: int,
    data: TaskLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Log work progress note during execution."""
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    tech_id = current_user.technician_profile.id if current_user.technician_profile else 1

    task_log = TaskLog(
        request_id=req.id,
        technician_id=tech_id,
        note=data.note,
        duration_minutes=data.duration_minutes,
        created_at=utcnow()
    )
    db.add(task_log)
    db.commit()
    db.refresh(task_log)

    return {
        "id": task_log.id,
        "note": task_log.note,
        "duration_minutes": task_log.duration_minutes,
        "created_at": task_log.created_at.isoformat()
    }


@router.post("/requests/{id}/evidence")
async def upload_evidence(
    id: int,
    template_key: str = Form(...),
    type: str = Form("PHOTO"),
    text_value: Optional[str] = Form(None),
    lat: Optional[float] = Form(None),
    lng: Optional[float] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload photo evidence, test result, or checklist item with GPS coordinates."""
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    file_url = None
    if file:
        file_url = await save_upload_file(file, prefix=f"req_{req.id}_{template_key}")

    # Check Proof of Presence
    presence_status, dist_m = check_proof_of_presence(req.site, lat, lng)

    # Check if this evidence item already exists; update or create
    existing_ev = (
        db.query(EvidenceItem)
        .filter(EvidenceItem.request_id == req.id, EvidenceItem.template_key == template_key)
        .first()
    )

    if existing_ev:
        existing_ev.file_url = file_url or existing_ev.file_url
        existing_ev.text_value = text_value or existing_ev.text_value
        existing_ev.lat = lat
        existing_ev.lng = lng
        existing_ev.presence_status = presence_status
        existing_ev.status = "SUBMITTED"
        existing_ev.captured_at = utcnow()
        db.commit()
        ev_item = existing_ev
    else:
        ev_item = EvidenceItem(
            request_id=req.id,
            template_key=template_key,
            type=type,
            file_url=file_url,
            text_value=text_value,
            submitted_by=current_user.id,
            lat=lat,
            lng=lng,
            presence_status=presence_status,
            status="SUBMITTED",
            captured_at=utcnow()
        )
        db.add(ev_item)
        db.commit()
        db.refresh(ev_item)

    # Return completeness score
    completeness = calculate_evidence_completeness(db, req)

    return {
        "id": ev_item.id,
        "template_key": ev_item.template_key,
        "status": ev_item.status,
        "presence_status": presence_status,
        "distance_meters": dist_m,
        "completeness": completeness
    }


@router.post("/requests/{id}/complete")
def submit_completion(
    id: int,
    current_user: User = Depends(require_role(["TECHNICIAN", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """Technician submits job completion.
    Domain Guard: Enforces all technician-side mandatory evidence items exist.
    Transitions IN_PROGRESS -> COMPLETED.
    """
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    transition(
        db=db,
        request=req,
        to_status="COMPLETED",
        actor_role=current_user.role,
        actor_id=current_user.id,
        actor_name=current_user.name,
        reason="Technician uploaded all required evidence and completed repair."
    )

    # Mark active assignment completed
    asg = (
        db.query(Assignment)
        .filter(Assignment.request_id == req.id, Assignment.status != "REPLACED")
        .order_by(Assignment.id.desc())
        .first()
    )
    if asg:
        asg.status = "COMPLETED"
        db.commit()

    return {
        "status": "COMPLETED",
        "completed_at": req.completed_at.isoformat(),
        "message": "Job marked as completed. Awaiting supervisor evidence verification."
    }
