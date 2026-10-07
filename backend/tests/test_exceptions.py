"""Test suite for exception rules, What-If simulator, and Hot-Swap."""
import pytest
import uuid
from app.db.session import SessionLocal
from app.db.models import ServiceRequest, Assignment, Technician, ExceptionFlag, User, Machine, FaultCategory
from app.services.exceptions import raise_exception_flag, get_what_if_options, execute_hotswap
from app.core.time import utcnow


def test_exception_flag_and_hotswap():
    db = SessionLocal()
    try:
        machine = db.query(Machine).filter(Machine.code == "M-104").first()
        fault = db.query(FaultCategory).first()
        t07 = db.query(Technician).filter(Technician.code == "T-07").first()
        t02 = db.query(Technician).filter(Technician.code == "T-02").first()
        admin = db.query(User).filter(User.role == "ADMIN").first()

        # Create active assigned request
        req = ServiceRequest(
            code=f"SR-EXC-TEST-{uuid.uuid4().hex[:4]}",
            machine_id=machine.id,
            site_id=machine.site_id,
            raised_by=admin.id,
            source="WEB",
            fault_category_id=fault.id,
            description="Testing exception and hot-swap",
            priority="HIGH",
            effective_priority="HIGH",
            status="ASSIGNED",
            track_token=uuid.uuid4().hex,
            created_at=utcnow()
        )
        db.add(req)
        db.commit()

        asg = Assignment(
            request_id=req.id,
            technician_id=t07.id,
            plan_type="BEST_FIT",
            match_score=95.0,
            status="ASSIGNED",
            eta_minutes=20.0,
            created_at=utcnow()
        )
        db.add(asg)
        db.commit()

        # Raise exception flag (transitions req from ASSIGNED to EXCEPTION)
        flag = raise_exception_flag(
            db=db,
            request=req,
            rule_code="TECH_DECLINE",
            severity="WARNING",
            reason="Technician unavailable",
            blocker="Technician dropout",
            recommended_action="Execute Hot-Swap",
            owner_role="MANAGER"
        )
        assert flag.id is not None
        assert flag.status == "OPEN"
        assert req.status == "EXCEPTION"

        # What-If simulator options
        options_data = get_what_if_options(db, flag.id)
        assert len(options_data["options"]) > 0
        assert "wait_option" in options_data

        # Execute Hot-Swap to T-02
        updated_req = execute_hotswap(
            db=db,
            exception_id=flag.id,
            new_technician_id=t02.id,
            actor_id=admin.id,
            actor_role="MANAGER",
            reason="Test hot-swap execution"
        )
        assert updated_req.status == "ASSIGNED"
        assert flag.status == "RESOLVED"

    finally:
        db.close()
