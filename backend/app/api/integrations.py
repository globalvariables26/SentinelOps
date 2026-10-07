"""External Integrations: IoT Sensor Webhook, Telegram Bot, and Extensibility status."""
import uuid
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import SensorReading, Machine, ServiceRequest, FaultCategory
from app.core.config import settings
from app.core.time import utcnow
from app.services.validation import run_full_validation
from app.services.workflow import transition
from app.schemas.schemas import IoTWebhookPayload

router = APIRouter(prefix="/integrations", tags=["Extensibility & Integrations"])


@router.post("/iot/webhook")
def receive_iot_sensor_data(
    payload: IoTWebhookPayload,
    x_api_key: str = Header(None),
    db: Session = Depends(get_db)
):
    """Ingest live IoT machine telemetry.
    If vibration (>4.5 mm/s) or temperature (>85°C) exceeds safety threshold,
    automatically creates an automated source=IOT service request through the full workflow.
    """
    if x_api_key != settings.IOT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid IoT API Key.")

    machine = db.query(Machine).filter(Machine.code == payload.machine_code).first()
    if not machine:
        raise HTTPException(status_code=404, detail=f"Machine '{payload.machine_code}' not found.")

    # Record sensor reading
    reading = SensorReading(
        machine_id=machine.id,
        metric=payload.metric,
        value=payload.value,
        ts=utcnow()
    )
    db.add(reading)
    db.commit()

    # Threshold Check
    is_anomaly = False
    fault_code = "CAT-VIB"
    if payload.metric.lower() == "vibration" and payload.value > 4.5:
        is_anomaly = True
        fault_code = "CAT-BRG"  # Vibration indicates bearing wear
    elif payload.metric.lower() == "temperature" and payload.value > 85.0:
        is_anomaly = True
        fault_code = "CAT-HYD"

    created_request = None
    if is_anomaly:
        fault = db.query(FaultCategory).filter(FaultCategory.code == fault_code).first() or db.query(FaultCategory).first()
        req_code = f"SR-IOT-{machine.code}-{uuid.uuid4().hex[:4].upper()}"

        # Run validation
        val_report = run_full_validation(db, machine.id, fault.id, "CRITICAL")
        sla_info = val_report["sla"]

        new_req = ServiceRequest(
            code=req_code,
            machine_id=machine.id,
            site_id=machine.site_id,
            raised_by=1,  # Admin / System user
            source="IOT",
            fault_category_id=fault.id,
            description=f"Automated IoT Trigger: Anomaly on metric '{payload.metric}' reached {payload.value} (Threshold exceeded).",
            priority="CRITICAL",
            effective_priority="CRITICAL",
            priority_boost_reason="Autonomous telemetry threshold violation",
            status="CREATED",
            expected_duration_h=fault.expected_duration_h,
            sla_due_at=datetime.fromisoformat(sla_info["sla_due_at"]),
            response_due_at=datetime.fromisoformat(sla_info["ack_due_at"]),
            validation_report=json.dumps(val_report),
            readiness_score=80.0,
            risk_ratio=0.1,
            risk_level="SAFE",
            track_token=uuid.uuid4().hex,
            created_at=utcnow()
        )
        db.add(new_req)
        db.commit()
        db.refresh(new_req)

        transition(db, new_req, "VALIDATED", actor_role="SYSTEM", reason="IoT telemetry validated")
        transition(db, new_req, "PENDING_APPROVAL", actor_role="SYSTEM", reason="Automated IoT breakdown queued for manager approval")
        created_request = {"id": new_req.id, "code": new_req.code}

    return {
        "status": "INGESTED",
        "machine": machine.code,
        "metric": payload.metric,
        "value": payload.value,
        "anomaly_triggered": is_anomaly,
        "service_request": created_request
    }


@router.get("/status")
def get_integrations_status():
    """Return status of all integration plug-in adapters."""
    return {
        "iot": {
            "endpoint": "/api/integrations/iot/webhook",
            "api_key_configured": bool(settings.IOT_API_KEY),
            "status": "ACTIVE"
        },
        "telegram": {
            "bot_configured": bool(settings.TELEGRAM_BOT_TOKEN),
            "status": "ACTIVE" if settings.TELEGRAM_BOT_TOKEN else "SIMULATED (Console Logging)"
        },
        "ai_engine": {
            "provider": "Google Gemini" if settings.GEMINI_API_KEY else "Deterministic Rule-Based Fallback",
            "model": settings.GEMINI_MODEL,
            "status": "ACTIVE"
        },
        "storage": {
            "backend": settings.STORAGE_BACKEND,
            "status": "ACTIVE"
        }
    }
