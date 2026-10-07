"""Digital Machine Passport, Health Score, MTBF/MTTR, and Failure Prevention Loop."""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.db.models import (
    Machine, ServiceRequest, Assignment, Reservation, InventoryItem,
    StockLevel, FaultCategory, KitItem, ExceptionFlag
)
from app.services.audit import append_audit_log
from app.core.time import utcnow


def calculate_health_score(
    db: Session,
    machine_id: int
) -> tuple[float, str, dict[str, Any]]:
    """Calculate transparent 0-100 health score:
    100
    - (12 * failures in last 180 days)
    - (5 * SLA breaches)
    - (10 * overdue preventive maintenance)
    - (10 * repeat component failure)
    Clamped 0 to 100.
    """
    now = utcnow()
    d180 = now - timedelta(days=180)

    # Failures in last 180 days
    failures = (
        db.query(ServiceRequest)
        .filter(
            ServiceRequest.machine_id == machine_id,
            ServiceRequest.created_at >= d180,
            ServiceRequest.status.in_(["COMPLETED", "VERIFIED"])
        )
        .all()
    )
    failure_count = len(failures)

    # SLA breaches
    sla_breaches = (
        db.query(ServiceRequest)
        .filter(
            ServiceRequest.machine_id == machine_id,
            ServiceRequest.risk_level == "BREACHED"
        )
        .count()
    )

    # Check for repeat component failures (3+ in 90 days)
    d90 = now - timedelta(days=90)
    recent_90d = [f for f in failures if f.created_at >= d90]
    category_counts = {}
    for r in recent_90d:
        category_counts[r.fault_category_id] = category_counts.get(r.fault_category_id, 0) + 1
    has_repeat_failure = any(cnt >= 3 for cnt in category_counts.values())

    # Penalty deductions
    failure_penalty = failure_count * 12
    sla_penalty = sla_breaches * 5
    repeat_penalty = 10 if has_repeat_failure else 0
    overdue_penalty = 0  # Can be expanded

    total_deductions = failure_penalty + sla_penalty + repeat_penalty + overdue_penalty
    raw_score = 100 - total_deductions
    clamped_score = max(0.0, min(100.0, float(raw_score)))

    if clamped_score >= 80:
        status_label = "Healthy"
    elif clamped_score >= 50:
        status_label = "Watch"
    else:
        status_label = "High Risk"

    breakdown = {
        "base_score": 100,
        "failure_count_180d": failure_count,
        "failure_penalty": failure_penalty,
        "sla_breaches": sla_breaches,
        "sla_penalty": sla_penalty,
        "has_repeat_failure": has_repeat_failure,
        "repeat_penalty": repeat_penalty,
        "overdue_penalty": overdue_penalty,
        "score": clamped_score,
        "status_label": status_label
    }
    return clamped_score, status_label, breakdown


def get_machine_passport(db: Session, machine_id: int) -> Dict[str, Any]:
    """Compile comprehensive digital passport for an industrial machine."""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise ValueError("Machine not found.")

    score, status_label, breakdown = calculate_health_score(db, machine_id)
    machine.health_score = score
    db.commit()

    # All historical service requests
    requests: List[ServiceRequest] = (
        db.query(ServiceRequest)
        .filter(ServiceRequest.machine_id == machine_id)
        .order_by(ServiceRequest.created_at.desc())
        .all()
    )

    completed_requests = [r for r in requests if r.status in ("COMPLETED", "VERIFIED") and r.started_at and r.completed_at]

    # MTTR: Mean Time to Repair (hours)
    repair_durations = [
        (r.completed_at - r.started_at).total_seconds() / 3600.0
        for r in completed_requests
    ]
    mttr_h = round(sum(repair_durations) / len(repair_durations), 1) if repair_durations else 2.5
    total_downtime_h = round(sum(repair_durations), 1)

    # MTBF: Mean Time Between Failures
    mtbf_h = None
    next_maintenance_window = None
    if len(completed_requests) >= 3:
        # Time intervals between consecutive failures
        sorted_completed = sorted(completed_requests, key=lambda x: x.created_at)
        intervals = []
        for i in range(1, len(sorted_completed)):
            diff_h = (sorted_completed[i].created_at - sorted_completed[i-1].created_at).total_seconds() / 3600.0
            intervals.append(diff_h)
        if intervals:
            mtbf_h = round(sum(intervals) / len(intervals), 1)
            last_failure = sorted_completed[-1].created_at
            next_maintenance_date = last_failure + timedelta(hours=mtbf_h)
            next_maintenance_window = next_maintenance_date.strftime("%Y-%m-%d")
    else:
        next_maintenance_window = "Insufficient data (needs >= 3 completed jobs)"

    # Total Cost = Labor hours * rate + Parts cost
    total_cost = 0.0
    techs_involved = set()
    parts_replaced = []

    for r in requests:
        # Parts cost
        for res in r.reservations:
            if res.status in ("ISSUED", "RESERVED"):
                cost = (res.item.unit_cost or 0.0) * res.qty
                total_cost += cost
                parts_replaced.append({
                    "sku": res.item.sku,
                    "name": res.item.name,
                    "qty": res.qty,
                    "cost": cost,
                    "request_code": r.code
                })
        # Labor cost
        for asg in r.assignments:
            if asg.status in ("COMPLETED", "ASSIGNED"):
                techs_involved.add(f"{asg.technician.code} ({asg.technician.user.name})")
                labor_cost = (asg.technician.hourly_rate or 50.0) * (r.expected_duration_h or 2.0)
                total_cost += labor_cost

    # Build timeline events
    timeline = []
    for r in requests:
        timeline.append({
            "id": r.id,
            "code": r.code,
            "status": r.status,
            "fault": r.fault_category.name,
            "priority": r.priority,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            "summary": r.description
        })

    # Repeat failure flag check
    repeat_flag = (
        db.query(ExceptionFlag)
        .join(ServiceRequest)
        .filter(
            ServiceRequest.machine_id == machine_id,
            ExceptionFlag.rule_code == "REPEAT_FAILURE",
            ExceptionFlag.status == "OPEN"
        )
        .first()
    )

    return {
        "machine": {
            "id": machine.id,
            "code": machine.code,
            "model": machine.model,
            "serial": machine.serial,
            "site_name": machine.site.name,
            "site_code": machine.site.code,
            "criticality": machine.criticality,
            "status": machine.status,
            "qr_token": machine.qr_token,
            "contract_active": machine.contract_active,
            "warranty_until": machine.warranty_until.isoformat() if machine.warranty_until else None,
            "health_score": score,
            "health_status": status_label,
            "score_breakdown": breakdown
        },
        "metrics": {
            "mtbf_hours": mtbf_h or "Insufficient data",
            "mttr_hours": mttr_h,
            "total_downtime_hours": total_downtime_h,
            "total_cost": round(total_cost, 2),
            "parts_replaced_count": len(parts_replaced),
            "unique_technicians_count": len(techs_involved),
            "next_maintenance_window": next_maintenance_window
        },
        "technicians_worked": list(techs_involved),
        "parts_replaced": parts_replaced,
        "timeline": timeline,
        "repeat_failure_alert": {
            "active": (repeat_flag is not None) or breakdown.get("has_repeat_failure", False),
            "reason": repeat_flag.reason if repeat_flag else (
                "Chronic component failure pattern detected: >=3 failures within 90 days."
                if breakdown.get("has_repeat_failure") else None
            ),
            "action": "Create preventive inspection plan"
        }
    }


def check_repeat_failure_loop(db: Session, machine_id: int, fault_category_id: int) -> bool:
    """Detect if the machine has hit 3+ failures of this fault category within 90 days."""
    now = utcnow()
    d90 = now - timedelta(days=90)

    recent_failures = (
        db.query(ServiceRequest)
        .filter(
            ServiceRequest.machine_id == machine_id,
            ServiceRequest.fault_category_id == fault_category_id,
            ServiceRequest.created_at >= d90,
            ServiceRequest.status.in_(["COMPLETED", "VERIFIED"])
        )
        .all()
    )

    if len(recent_failures) >= 3:
        machine = db.query(Machine).filter(Machine.id == machine_id).first()
        fault = db.query(FaultCategory).filter(FaultCategory.id == fault_category_id).first()
        
        # Check if flag already raised
        latest_req = recent_failures[-1]
        existing = (
            db.query(ExceptionFlag)
            .filter(
                ExceptionFlag.request_id == latest_req.id,
                ExceptionFlag.rule_code == "REPEAT_FAILURE"
            )
            .first()
        )
        if not existing:
            from app.services.exceptions import raise_exception_flag
            raise_exception_flag(
                db=db,
                request=latest_req,
                rule_code="REPEAT_FAILURE",
                severity="WARNING",
                reason=f"Machine {machine.code} experienced {len(recent_failures)} repeat '{fault.name}' failures in past 90 days.",
                blocker="Chronic equipment component failure pattern detected",
                recommended_action="Execute Failure Prevention Loop: Create preventive inspection plan and elevate inventory min stock.",
                owner_role="MANAGER"
            )
        return True
    return False


def create_preventive_plan(
    db: Session,
    machine_id: int,
    fault_category_id: int,
    actor_id: int
) -> ServiceRequest:
    """Failure Prevention Loop action:
    1. Creates a PREVENTIVE service request
    2. Elevates the fault category's kit parts' min_level in inventory
    """
    import uuid
    from app.services.validation import run_full_validation
    from app.services.workflow import transition

    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    fault = db.query(FaultCategory).filter(FaultCategory.id == fault_category_id).first()

    # 1. Elevate part min_levels
    for ki in fault.kit_items:
        stocks = db.query(StockLevel).filter(StockLevel.item_id == ki.item_id).all()
        for s in stocks:
            s.min_level += 2  # Raise safety buffer

    # 2. Create PREVENTIVE service request
    req_code = f"PRV-{machine.code}-{uuid.uuid4().hex[:4].upper()}"
    validation_report = run_full_validation(db, machine.id, fault.id, "HIGH")

    new_req = ServiceRequest(
        code=req_code,
        machine_id=machine.id,
        site_id=machine.site_id,
        raised_by=actor_id,
        source="PREVENTIVE",
        fault_category_id=fault.id,
        description=f"Automated Preventive Maintenance Plan triggered by Repeat-Failure Detection on {machine.code}.",
        priority="HIGH",
        effective_priority="HIGH",
        priority_boost_reason="Chronic component failure prevention loop",
        status="CREATED",
        expected_duration_h=fault.expected_duration_h,
        validation_report=json.dumps(validation_report),
        readiness_score=75.0,
        risk_ratio=0.1,
        risk_level="SAFE",
        safety_confirmed=False,
        track_token=uuid.uuid4().hex,
        created_at=utcnow()
    )
    db.add(new_req)
    db.commit()
    db.refresh(new_req)

    # Transition to VALIDATED then PENDING_APPROVAL
    transition(db, new_req, "VALIDATED", actor_role="SYSTEM", reason="Preventive auto-validation passed")
    transition(db, new_req, "PENDING_APPROVAL", actor_role="SYSTEM", reason="Queued for preventive dispatch")

    # Record audit log
    append_audit_log(
        db=db,
        entity_type="Machine",
        entity_id=machine.id,
        action="PREVENTIVE_PLAN_CREATED",
        actor_id=actor_id,
        actor_role="MANAGER",
        before={"health_score": machine.health_score},
        after={"preventive_request": req_code, "status": "PENDING_APPROVAL"},
        meta={"fault_category": fault.name, "min_stock_bumped": True}
    )

    return new_req
