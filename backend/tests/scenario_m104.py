"""End-to-End Scenario Test for Machine M-104 (The Core Demo Story).
Exercises the complete lifecycle through the API and asserts every milestone:
1. Machine M-104 Request Creation & Auto-Validation
2. Bearing X Shortage & Inter-Site Transfer Impact Chain
3. Explainable 3-Plan Generation & Dispatch Approval
4. Technician Dropout, What-If Simulation, and One-Click Hot-Swap
5. Field Execution, Proof of Presence, and Evidence Upload
6. Evidence Gating & Supervisor Verification
7. Digital Machine Passport & Failure Prevention Loop
8. Cryptographic Hash Chain Verification & Tamper Detection
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.seed import seed_database
from app.db.models import Machine, FaultCategory, ServiceRequest, ExceptionFlag, User

client = TestClient(app)


def test_full_m104_service_lifecycle():
    # 0. Ensure fresh clean seed state
    seed_database(reset=True)
    db = SessionLocal()

    # Logins
    login_admin = client.post("/api/auth/login", json={"email": "admin@sentinelops.com", "password": "admin123"}).json()
    admin_token = login_admin["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    login_manager = client.post("/api/auth/login", json={"email": "manager@sentinelops.com", "password": "manager123"}).json()
    manager_token = login_manager["access_token"]
    manager_headers = {"Authorization": f"Bearer {manager_token}"}

    login_supervisor = client.post("/api/auth/login", json={"email": "supervisor@sentinelops.com", "password": "supervisor123"}).json()
    sup_token = login_supervisor["access_token"]
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

    login_tech = client.post("/api/auth/login", json={"email": "tech07@sentinelops.com", "password": "tech123"}).json()
    tech_token = login_tech["access_token"]
    tech_headers = {"Authorization": f"Bearer {tech_token}"}

    # Step 1: Lookup Machine M-104 and Bearing Fault Category
    m104 = db.query(Machine).filter(Machine.code == "M-104").first()
    assert m104 is not None
    bearing_cat = db.query(FaultCategory).filter(FaultCategory.code == "CAT-BRG").first()
    assert bearing_cat is not None

    # Step 2: Customer creates Critical breakdown request
    create_resp = client.post(
        "/api/requests",
        json={
            "machine_id": m104.id,
            "fault_category_id": bearing_cat.id,
            "description": "Loud grinding noise and excessive spindle vibration on M-104 main hydraulic press.",
            "priority": "HIGH",
            "source": "QR"
        },
        headers=admin_headers
    )
    assert create_resp.status_code == 200
    req_data = create_resp.json()
    req_id = req_data["id"]
    assert req_data["status"] == "PENDING_APPROVAL"
    assert req_data["effective_priority"] == "CRITICAL"  # Boosted by machine criticality and category

    # Step 3: Fetch Request Detail & Verify Spare-Part Impact Chain (Bearing X shortage)
    detail_resp = client.get(f"/api/requests/{req_id}", headers=manager_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    
    # Assert Impact Chain identifies Bearing X shortage and recommends transfer from Site B
    impact = detail["impact_chain"]
    assert impact["has_impact"] is True
    assert "Site B" in impact["recommended_recovery"]
    assert detail["readiness"]["score"] > 0

    # Step 4: Verify 3 Explainable Plans & Approve Best Fit (T-07 Rahul)
    plans = detail["plans"]
    assert len(plans) == 3
    best_fit = next(p for p in plans if p["plan_type"] == "BEST_FIT")
    assert best_fit["technician"]["code"] == "T-07"
    assert "HP-500" in best_fit["explanation"] or "HydraPress" in best_fit["explanation"] or "T-07" in best_fit["explanation"]

    approve_resp = client.post(
        f"/api/requests/{req_id}/approve",
        json={"plan_type": "BEST_FIT", "safety_confirmed": True},
        headers=manager_headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "ASSIGNED"

    # Step 5: Simulate Technician Dropout (Chaos: Technician Declines)
    chaos_decline = client.post("/api/demo/decline", headers=admin_headers)
    assert chaos_decline.status_code == 200
    assert chaos_decline.json()["request_id"] == req_id
    exception_id = chaos_decline.json()["exception_id"]

    # Step 6: What-If Rescue Simulator & One-Click Hot-Swap
    whatif_resp = client.get(f"/api/exceptions/{exception_id}/options", headers=manager_headers)
    assert whatif_resp.status_code == 200
    whatif_data = whatif_resp.json()
    assert len(whatif_data["options"]) > 0
    assert "wait_option" in whatif_data

    # Execute Hot-Swap to top replacement
    replacement_tech_id = whatif_data["options"][0]["technician"]["id"]
    hotswap_resp = client.post(
        f"/api/exceptions/{exception_id}/hotswap",
        json={"technician_id": replacement_tech_id, "reason": "Manager executed one-click Hot-Swap"},
        headers=manager_headers
    )
    assert hotswap_resp.status_code == 200
    assert hotswap_resp.json()["status"] == "ASSIGNED"

    # Step 7: Technician Field Flow (Ack, Check-In, Safety Confirm, Start)
    req_updated = client.get(f"/api/requests/{req_id}", headers=admin_headers).json()
    new_asg_id = req_updated["active_assignment"]["id"]

    ack_resp = client.post(f"/api/assignments/{new_asg_id}/acknowledge", headers=admin_headers)
    assert ack_resp.status_code == 200

    checkin_resp = client.post(
        f"/api/assignments/{new_asg_id}/checkin",
        json={"lat": 13.0827, "lng": 80.1542},  # Inside Site A boundary
        headers=admin_headers
    )
    assert checkin_resp.status_code == 200
    assert checkin_resp.json()["presence_status"] == "VERIFIED"

    start_resp = client.post(
        f"/api/assignments/{new_asg_id}/start",
        json={"safety_confirmed": True},
        headers=admin_headers
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "IN_PROGRESS"

    # Step 8: Log Task Progress Note
    task_resp = client.post(
        f"/api/requests/{req_id}/tasks",
        json={"note": "Extracted damaged roller bearing using hydraulic puller; cleaned housing.", "duration_minutes": 45},
        headers=admin_headers
    )
    assert task_resp.status_code == 200

    # Step 9: Evidence Gating — Incomplete submission blocked
    # Attempting complete before all evidence uploaded must fail
    fail_complete = client.post(f"/api/requests/{req_id}/complete", headers=admin_headers)
    assert fail_complete.status_code == 400
    assert "Missing mandatory technician evidence" in fail_complete.json()["detail"]

    # Upload all mandatory technician evidence
    tech_keys = ["before_photo", "serial_check", "after_photo", "checklist", "test_run"]
    for k in tech_keys:
        ev_resp = client.post(
            f"/api/requests/{req_id}/evidence",
            data={
                "template_key": k,
                "type": "PHOTO" if "photo" in k else "CHECKLIST",
                "text_value": f"Verified check for {k}",
                "lat": 13.0827,
                "lng": 80.1542
            },
            headers=admin_headers
        )
        assert ev_resp.status_code == 200

    # Submit completion now succeeds
    complete_resp = client.post(f"/api/requests/{req_id}/complete", headers=admin_headers)
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "COMPLETED"

    # Step 10: Supervisor Verification
    # Complete remaining signoffs
    client.post(
        f"/api/requests/{req_id}/evidence",
        data={"template_key": "customer_signoff", "type": "SIGN_OFF", "text_value": "Suresh Nair approved"},
        headers=admin_headers
    )
    client.post(
        f"/api/requests/{req_id}/evidence",
        data={"template_key": "supervisor_approval", "type": "SIGN_OFF", "text_value": "Karthik Raja verified"},
        headers=admin_headers
    )

    verify_resp = client.post(f"/api/requests/{req_id}/verify", headers=sup_headers)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "VERIFIED"

    # Step 11: Machine Passport & Failure Prevention Loop
    passport_resp = client.get(f"/api/machines/{m104.id}/passport", headers=admin_headers)
    assert passport_resp.status_code == 200
    passport = passport_resp.json()
    assert passport["metrics"]["total_cost"] > 0
    assert passport["repeat_failure_alert"]["active"] is True

    # Step 12: Trigger Failure Prevention Loop (Preventive Inspection Plan)
    prev_resp = client.post(
        f"/api/machines/{m104.id}/preventive-plan?fault_category_id={bearing_cat.id}",
        headers=manager_headers
    )
    assert prev_resp.status_code == 200
    assert "PRV-" in prev_resp.json()["request_code"]

    # Step 13: Cryptographic Audit Log Verification & Tampering Detection
    audit_verify = client.get("/api/audit/verify")
    assert audit_verify.status_code == 200
    assert audit_verify.json()["is_valid"] is True

    # Tamper with entry #2 and verify detection
    tamper_resp = client.post("/api/demo/tamper-audit?seq=2", headers=admin_headers)
    assert tamper_resp.status_code == 200

    audit_verify_after = client.get("/api/audit/verify")
    assert audit_verify_after.json()["is_valid"] is False
    assert audit_verify_after.json()["broken_seq"] == 2

    # Step 14: Public Live Customer Tracker Check
    track_resp = client.get(f"/api/track/{detail['track_token']}")
    assert track_resp.status_code == 200
    assert track_resp.json()["request_code"] == req_data["code"]
    assert len(track_resp.json()["timeline"]) > 0

    print("\n✅ Scenario M-104 End-to-End Test PASSED with 100% assertions satisfied!")
    db.close()
