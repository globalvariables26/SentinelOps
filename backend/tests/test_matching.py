"""Test suite for MatchScore calculations and 3-Plan builder."""
import pytest
from app.db.session import SessionLocal
from app.db.models import ServiceRequest, Machine, Technician, FaultCategory
from app.services.matching import calculate_match_score, build_3_plans


def test_matching_engine_and_3_plans():
    db = SessionLocal()
    try:
        # Fetch M-104 request or recent request
        req = db.query(ServiceRequest).filter(ServiceRequest.code.like("SR-104-HIST%")).first()
        assert req is not None

        # T-07 (Rahul) must have top MatchScore and certification
        t07 = db.query(Technician).filter(Technician.code == "T-07").first()
        assert t07 is not None

        eligible, score, breakdown, explanation = calculate_match_score(db, t07, req)
        assert eligible is True
        assert score >= 90.0
        assert breakdown["has_certification"] is True
        assert "HP-500" in explanation or "HydraPress" in explanation or "T-07" in explanation

        # Plan Builder must return 3 plans
        plans = build_3_plans(db, req)
        assert len(plans) == 3
        plan_types = {p["plan_type"] for p in plans}
        assert "BEST_FIT" in plan_types
        assert "FASTEST" in plan_types
        assert "LEAST_DISRUPTIVE" in plan_types

    finally:
        db.close()
