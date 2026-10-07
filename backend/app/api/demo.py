"""Chaos Panel and Demo Fast-Forward Endpoints (DEMO_MODE only)."""
import json
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import ServiceRequest, Assignment, StockLevel, ExceptionFlag, InventoryItem, Machine
from app.core.config import settings
from app.core.deps import require_role
from app.core.time import utcnow
from app.services.exceptions import raise_exception_flag
from app.services.matching import build_3_plans
from app.services.audit import append_audit_log, tamper_audit_log
from app.schemas.schemas import FastForwardRequest

router = APIRouter(prefix="/demo", tags=["Chaos Panel & Demo Controller"])


def verify_demo_mode():
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Demo Chaos endpoints are only enabled when DEMO_MODE=true.")


@router.post("/decline")
def chaos_technician_decline(db: Session = Depends(get_db)):
    """Simulate assigned technician declining their job on demand."""
    verify_demo_mode()
    # Find latest ASSIGNED request
    asg = (
        db.query(Assignment)
        .filter(Assignment.status == "ASSIGNED")
        .order_by(Assignment.id.desc())
        .first()
    )
    if not asg:
        raise HTTPException(status_code=400, detail="No active ASSIGNED job found to decline.")

    asg.status = "DECLINED"
    asg.replaced_reason = "[SIMULATED] Technician family emergency / sudden decline"
    req = asg.service_request

    # Compute top 3 replacements
    options = build_3_plans(db, req, exclude_tech_ids=[asg.technician_id])

    flag = raise_exception_flag(
        db=db,
        request=req,
        rule_code="TECH_DECLINE",
        severity="WARNING",
        reason=f"[SIMULATED] Technician {asg.technician.code} ({asg.technician.user.name}) declined dispatch.",
        blocker="Technician dropout",
        recommended_action="Execute Hot-Swap to reassign immediately to top alternate candidate.",
        owner_role="MANAGER",
        options_snapshot=options
    )

    append_audit_log(
        db=db,
        entity_type="Assignment",
        entity_id=asg.id,
        action="[SIMULATED] TECHNICIAN_DECLINED",
        actor_id=asg.technician.user_id,
        actor_role="TECHNICIAN",
        meta={"reason": asg.replaced_reason}
    )

    return {
        "message": f"Technician {asg.technician.code} declined {req.code}.",
        "exception_id": flag.id,
        "request_id": req.id
    }


@router.post("/noshow")
def chaos_technician_noshow(db: Session = Depends(get_db)):
    """Simulate technician failing to arrive at site."""
    verify_demo_mode()
    asg = (
        db.query(Assignment)
        .filter(Assignment.status == "ASSIGNED")
        .order_by(Assignment.id.desc())
        .first()
    )
    if not asg:
        raise HTTPException(status_code=400, detail="No active ASSIGNED job found.")

    asg.status = "NO_SHOW"
    req = asg.service_request
    options = build_3_plans(db, req, exclude_tech_ids=[asg.technician_id])

    flag = raise_exception_flag(
        db=db,
        request=req,
        rule_code="TECH_NO_SHOW",
        severity="CRITICAL",
        reason=f"[SIMULATED] Technician {asg.technician.code} failed to arrive within grace window.",
        blocker="Technician no-show at site",
        recommended_action="Initiate emergency Hot-Swap reassignment.",
        owner_role="MANAGER",
        options_snapshot=options
    )

    return {"message": f"No-show registered for {asg.technician.code}.", "exception_id": flag.id}


@router.post("/part-out")
def chaos_part_stockout(db: Session = Depends(get_db)):
    """Zero out Bearing X inventory to trigger part shortage scenario live."""
    verify_demo_mode()
    item = db.query(InventoryItem).filter(InventoryItem.sku == "SKU-BRG-X").first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    stocks = db.query(StockLevel).filter(StockLevel.item_id == item.id).all()
    for s in stocks:
        s.on_hand = 0
    db.commit()

    append_audit_log(
        db=db,
        entity_type="InventoryItem",
        entity_id=item.id,
        action="[SIMULATED] STOCK_DEPLETED",
        actor_id=1,
        actor_role="ADMIN",
        meta={"sku": item.sku}
    )

    return {"message": "Bearing X inventory depleted to 0 across all sites to simulate shortage."}


@router.post("/sla-fast-forward")
def chaos_fast_forward_sla(
    data: FastForwardRequest,
    db: Session = Depends(get_db)
):
    """Time-shift created_at backwards by X hours on active requests to trigger SLA risk escalation."""
    verify_demo_mode()
    active_reqs = (
        db.query(ServiceRequest)
        .filter(ServiceRequest.status.in_(["ASSIGNED", "IN_PROGRESS", "EXCEPTION"]))
        .all()
    )
    from app.services.sla import calculate_sla_risk

    shifted = 0
    for req in active_reqs:
        req.created_at = req.created_at - timedelta(hours=data.hours)
        ratio, level = calculate_sla_risk(db, req)
        req.risk_ratio = ratio
        req.risk_level = level
        shifted += 1

    db.commit()

    append_audit_log(
        db=db,
        entity_type="System",
        entity_id=1,
        action="[SIMULATED] TIME_WARP_SLA_FAST_FORWARD",
        actor_id=1,
        actor_role="ADMIN",
        meta={"shifted_hours": data.hours, "affected_requests": shifted}
    )

    return {"message": f"Fast-forwarded {data.hours} hours across {shifted} active service request(s)."}


@router.post("/sensor-fault")
def chaos_sensor_fault(db: Session = Depends(get_db)):
    """Trigger simulated critical vibration spike on M-104."""
    verify_demo_mode()
    from app.api.integrations import receive_iot_sensor_data
    from app.schemas.schemas import IoTWebhookPayload

    payload = IoTWebhookPayload(
        machine_code="M-104",
        metric="vibration",
        value=6.8  # Critical threshold violation (>4.5)
    )
    res = receive_iot_sensor_data(payload=payload, x_api_key=settings.IOT_API_KEY, db=db)
    return {"message": "Simulated IoT sensor anomaly generated for M-104.", "result": res}


@router.post("/tamper-audit")
def chaos_tamper_audit(seq: int = 1, db: Session = Depends(get_db)):
    """Maliciously modify an audit row to demonstrate SHA-256 chain verification failure."""
    verify_demo_mode()
    success = tamper_audit_log(db, seq, new_action="[SIMULATED] TAMPERED_ACTION_WITHOUT_REHASH")
    if not success:
        raise HTTPException(status_code=404, detail=f"Audit entry seq #{seq} not found")

    return {
        "message": f"Tampered with audit entry #{seq}. Run 'Verify Integrity' to observe real-time cryptographic detection.",
        "tampered_seq": seq
    }


@router.post("/reset")
def chaos_reset_demo(db: Session = Depends(get_db)):
    """Idempotently re-seed clean demonstration dataset."""
    verify_demo_mode()
    from app.db.seed import seed_database
    seed_database(reset=True)
    return {"message": "SentinelOps database completely reset to pristine demonstration state."}
