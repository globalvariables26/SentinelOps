"""Test suite for strict workflow transitions and role guards."""
import pytest
import uuid
from fastapi import HTTPException
from app.db.session import SessionLocal
from app.db.models import ServiceRequest, Machine, FaultCategory, User
from app.services.workflow import transition
from app.core.time import utcnow


def test_allowed_and_forbidden_transitions():
    db = SessionLocal()
    try:
        machine = db.query(Machine).filter(Machine.code == "M-104").first()
        fault = db.query(FaultCategory).first()
        user = db.query(User).filter(User.role == "ADMIN").first()

        req = ServiceRequest(
            code=f"SR-TEST-{uuid.uuid4().hex[:4]}",
            machine_id=machine.id,
            site_id=machine.site_id,
            raised_by=user.id,
            source="WEB",
            fault_category_id=fault.id,
            description="Testing transition guards",
            priority="MEDIUM",
            effective_priority="MEDIUM",
            status="CREATED",
            track_token=uuid.uuid4().hex,
            created_at=utcnow()
        )
        db.add(req)
        db.commit()

        # 1. Allowed transition: CREATED -> VALIDATED by SYSTEM
        transition(db, req, "VALIDATED", actor_role="SYSTEM", reason="Auto-validation passed")
        assert req.status == "VALIDATED"

        # 2. Forbidden transition: VALIDATED -> COMPLETED (invalid transition path)
        with pytest.raises(HTTPException) as exc_info:
            transition(db, req, "COMPLETED", actor_role="ADMIN", reason="Illegal skip")
        assert exc_info.value.status_code == 400
        assert "Invalid status transition" in exc_info.value.detail

        # 3. Forbidden role: VALIDATED -> PENDING_APPROVAL by TECHNICIAN (role not allowed)
        with pytest.raises(HTTPException) as exc_info:
            transition(db, req, "PENDING_APPROVAL", actor_role="TECHNICIAN", reason="Unauthorized")
        assert exc_info.value.status_code == 403

        # 4. Allowed transition: VALIDATED -> PENDING_APPROVAL by SYSTEM
        transition(db, req, "PENDING_APPROVAL", actor_role="SYSTEM", reason="Auto-queued")
        assert req.status == "PENDING_APPROVAL"

        # 5. Allowed transition: PENDING_APPROVAL -> APPROVED by MANAGER
        transition(db, req, "APPROVED", actor_role="MANAGER", reason="Approved by dispatcher")
        assert req.status == "APPROVED"

        # 6. Terminal status test: CANCELLED cannot transition further
        transition(db, req, "CANCELLED", actor_role="MANAGER", reason="Cancelled by user")
        assert req.status == "CANCELLED"

        with pytest.raises(HTTPException) as exc_info:
            transition(db, req, "VALIDATED", actor_role="ADMIN", reason="Cannot uncancel")
        assert "Cannot transition from terminal status" in exc_info.value.detail

    finally:
        db.close()
