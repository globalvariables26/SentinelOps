"""Service Request lifecycle endpoints."""
import uuid
import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import ServiceRequest, Machine, Site, FaultCategory, User, Assignment
from app.core.deps import get_current_user
from app.services.validation import run_full_validation, compute_readiness_gate
from app.services.workflow import transition
from app.services.matching import build_3_plans
from app.services.sla import calculate_sla_risk
from app.services.copilot import parse_smart_intake
from app.schemas.schemas import RequestCreate, SmartIntakeRequest
from app.core.time import utcnow

router = APIRouter(prefix="/requests", tags=["Service Requests"])


@router.get("/fault-categories")
def list_fault_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List fault categories available for service-request creation."""
    categories = db.query(FaultCategory).order_by(FaultCategory.name.asc()).all()
    return [
        {
            "id": c.id,
            "code": c.code,
            "name": c.name,
            "description": c.description,
            "expected_duration_h": c.expected_duration_h,
            "priority_boost": c.priority_boost,
            "requires_certification": c.requires_certification,
        }
        for c in categories
    ]


@router.post("")
def create_service_request(
    data: RequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Raise a new service request. Runs the automated validation engine immediately."""
    machine = db.query(Machine).filter(Machine.id == data.machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # Tenancy check
    if current_user.role == "CUSTOMER" and current_user.customer_id and machine.site.customer_id != current_user.customer_id:
        raise HTTPException(status_code=403, detail="Machine does not belong to your organization")

    fault_cat = db.query(FaultCategory).filter(FaultCategory.id == data.fault_category_id).first()
    if not fault_cat:
        raise HTTPException(status_code=404, detail="Fault Category not found")

    # 1. Run validation engine
    validation_report = run_full_validation(
        db=db,
        machine_id=machine.id,
        fault_category_id=fault_cat.id,
        requested_priority=data.priority
    )

    req_code = f"SR-{machine.code}-{uuid.uuid4().hex[:4].upper()}"
    sla_info = validation_report["sla"]
    priority_info = validation_report["priority"]

    # Initial ServiceRequest record
    req = ServiceRequest(
        code=req_code,
        machine_id=machine.id,
        site_id=machine.site_id,
        raised_by=current_user.id,
        source=data.source,
        fault_category_id=fault_cat.id,
        description=data.description,
        priority=data.priority,
        effective_priority=priority_info["effective"],
        priority_boost_reason=priority_info["reason"],
        status="CREATED",
        expected_duration_h=fault_cat.expected_duration_h,
        sla_due_at=datetime.fromisoformat(sla_info["sla_due_at"]),
        response_due_at=datetime.fromisoformat(sla_info["ack_due_at"]),
        validation_report=json.dumps(validation_report),
        readiness_score=0.0,
        risk_ratio=0.1,
        risk_level="SAFE",
        safety_confirmed=False,
        track_token=uuid.uuid4().hex,
        created_at=utcnow()
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # 2. Check Machine Eligibility Gate
    if validation_report["machine_eligibility"]["status"] == "FAIL":
        transition(
            db=db,
            request=req,
            to_status="REJECTED",
            actor_role="SYSTEM",
            reason=f"Auto-validation failed: {validation_report['machine_eligibility']['reason']}"
        )
        return {"id": req.id, "code": req.code, "status": "REJECTED", "message": "Ineligible machine."}

    # 3. Transition to VALIDATED
    transition(
        db=db,
        request=req,
        to_status="VALIDATED",
        actor_role="SYSTEM",
        reason="Auto-validation checks passed successfully."
    )

    # 4. Compute initial Readiness Gate score
    readiness, passed_checks, missing_checks = compute_readiness_gate(db, req, validation_report)
    req.readiness_score = readiness
    db.commit()

    # 5. Check Service Kit to decide PENDING_APPROVAL vs ON_HOLD
    kit_check = validation_report.get("service_kit", {})
    if not kit_check.get("all_available") and not any(s.get("transfer_options") or s.get("substitutes") for s in kit_check.get("shortage_items", [])):
        transition(
            db=db,
            request=req,
            to_status="ON_HOLD",
            actor_role="SYSTEM",
            reason="Service kit missing on-site with no transfer or compatible substitute available."
        )
    else:
        transition(
            db=db,
            request=req,
            to_status="PENDING_APPROVAL",
            actor_role="SYSTEM",
            reason="Validated and queued for manager dispatch approval."
        )

    return {
        "id": req.id,
        "code": req.code,
        "status": req.status,
        "readiness_score": req.readiness_score,
        "effective_priority": req.effective_priority,
        "priority_boost_reason": req.priority_boost_reason,
        "risk_level": req.risk_level,
        "risk_ratio": req.risk_ratio,
        "sla": {
            "sla_due_at": req.sla_due_at.isoformat() if req.sla_due_at else None,
            "response_due_at": req.response_due_at.isoformat() if req.response_due_at else None,
        },
        "validation_report": validation_report,
        "track_token": req.track_token
    }


@router.post("/intake")
def smart_intake(data: SmartIntakeRequest, db: Session = Depends(get_db)):
    """Smart intake: parse free-form text description into a structured request draft."""
    draft = parse_smart_intake(db, data.text)
    return draft


@router.get("")
def list_service_requests(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    risk: Optional[str] = None,
    site_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List service requests with rich filters and multi-tenant security."""
    query = db.query(ServiceRequest).join(Machine).join(Site)

    if current_user.role == "CUSTOMER" and current_user.customer_id:
        query = query.filter(Site.customer_id == current_user.customer_id)
    elif current_user.role == "TECHNICIAN" and current_user.technician_profile:
        # Technicians see jobs assigned to them
        tech_id = current_user.technician_profile.id
        query = query.join(Assignment).filter(Assignment.technician_id == tech_id, Assignment.status != "REPLACED")

    if status:
        query = query.filter(ServiceRequest.status == status)
    if priority:
        query = query.filter(ServiceRequest.effective_priority == priority)
    if risk:
        query = query.filter(ServiceRequest.risk_level == risk)
    if site_id:
        query = query.filter(ServiceRequest.site_id == site_id)

    requests = query.order_by(ServiceRequest.created_at.desc()).all()
    results = []
    for r in requests:
        asg = (
            db.query(Assignment)
            .filter(Assignment.request_id == r.id, Assignment.status != "REPLACED")
            .order_by(Assignment.id.desc())
            .first()
        )
        results.append({
            "id": r.id,
            "code": r.code,
            "machine_code": r.machine.code,
            "machine_model": r.machine.model,
            "site_name": r.site.name,
            "fault_category": r.fault_category.name,
            "priority": r.priority,
            "effective_priority": r.effective_priority,
            "status": r.status,
            "readiness_score": r.readiness_score,
            "risk_level": r.risk_level,
            "risk_ratio": r.risk_ratio,
            "technician": f"{asg.technician.code} ({asg.technician.user.name})" if asg else "Unassigned",
            "sla_due_at": r.sla_due_at.isoformat() if r.sla_due_at else None,
            "created_at": r.created_at.isoformat(),
            "track_token": r.track_token
        })
    return results


@router.get("/{id}")
def get_service_request(id: int, db: Session = Depends(get_db)):
    """Fetch complete request details including readiness breakdown, SLA risk, impact chain, and plans."""
    req = db.query(ServiceRequest).filter(ServiceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    validation_data = json.loads(req.validation_report) if req.validation_report else {}
    readiness, passed_checks, missing_checks = compute_readiness_gate(db, req, validation_data)
    req.readiness_score = readiness
    
    # Calculate real-time SLA risk
    risk_ratio, risk_level = calculate_sla_risk(db, req)
    req.risk_ratio = risk_ratio
    req.risk_level = risk_level
    db.commit()

    # Build 3 dispatch plans
    plans = build_3_plans(db, req)

    # Active assignment
    active_asg = (
        db.query(Assignment)
        .filter(Assignment.request_id == req.id, Assignment.status != "REPLACED")
        .order_by(Assignment.id.desc())
        .first()
    )

    # Task logs
    task_logs = [
        {
            "id": tl.id,
            "note": tl.note,
            "technician": tl.technician.code,
            "duration_minutes": tl.duration_minutes,
            "created_at": tl.created_at.isoformat()
        }
        for tl in req.task_logs
    ]

    return {
        "id": req.id,
        "code": req.code,
        "machine": {
            "id": req.machine.id,
            "code": req.machine.code,
            "model": req.machine.model,
            "serial": req.machine.serial,
            "health_score": req.machine.health_score,
            "criticality": req.machine.criticality
        },
        "site": {
            "id": req.site.id,
            "code": req.site.code,
            "name": req.site.name,
            "lat": req.site.lat,
            "lng": req.site.lng,
            "access_notes": req.site.access_notes,
            "safety_requirements": req.site.safety_requirements
        },
        "fault_category": {
            "id": req.fault_category.id,
            "name": req.fault_category.name,
            "expected_duration_h": req.fault_category.expected_duration_h
        },
        "description": req.description,
        "priority": req.priority,
        "effective_priority": req.effective_priority,
        "priority_boost_reason": req.priority_boost_reason,
        "status": req.status,
        "safety_confirmed": req.safety_confirmed,
        "readiness": {
            "score": readiness,
            "passed": passed_checks,
            "missing": missing_checks,
            "is_ready": readiness >= 100.0
        },
        "sla": {
            "risk_ratio": risk_ratio,
            "risk_level": risk_level,
            "sla_due_at": req.sla_due_at.isoformat() if req.sla_due_at else None,
            "response_due_at": req.response_due_at.isoformat() if req.response_due_at else None
        },
        "validation_report": validation_data,
        "impact_chain": validation_data.get("impact_chain", {}),
        "plans": plans,
        "active_assignment": {
            "id": active_asg.id,
            "technician_id": active_asg.technician_id,
            "technician_code": active_asg.technician.code,
            "technician_name": active_asg.technician.user.name,
            "plan_type": active_asg.plan_type,
            "match_score": active_asg.match_score,
            "status": active_asg.status,
            "eta_minutes": active_asg.eta_minutes,
            "explanation": active_asg.explanation,
            "ack_due_at": active_asg.ack_due_at.isoformat() if active_asg.ack_due_at else None,
            "acknowledged_at": active_asg.acknowledged_at.isoformat() if active_asg.acknowledged_at else None
        } if active_asg else None,
        "task_logs": task_logs,
        "track_token": req.track_token,
        "created_at": req.created_at.isoformat()
    }
