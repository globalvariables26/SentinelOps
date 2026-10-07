"""Comprehensive idempotent database seed script for SentinelOps demo."""
import sys
import uuid
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.session import engine, SessionLocal
from app.db.base import Base
from app.core.security import get_password_hash
from app.core.time import utcnow
from app.services.audit import append_audit_log
from app.db.models import (
    Customer, Site, Machine, User, Technician, Skill, TechnicianSkill,
    TechnicianCertification, FaultCategory, FaultCategorySkill, InventoryItem,
    KitItem, EvidenceTemplateItem, StockLevel, ServiceRequest, Assignment,
    Reservation, ExceptionRule, ExceptionFlag, EvidenceItem
)


def seed_database(reset: bool = False):
    """Seed SentinelOps demo data idempotently."""
    if reset:
        print("Dropping existing tables for reset...")
        Base.metadata.drop_all(bind=engine)

    print("Creating tables if they do not exist...")
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        # Check if already seeded
        if db.query(User).count() > 0 and not reset:
            print("Database already contains records. Skipping seed.")
            return

        print("Seeding fresh demo dataset for SentinelOps...")
        now = utcnow()

        # 1. Customer
        customer = Customer(
            code="CUST-APEX",
            name="Apex Manufacturing Corp",
            contact_email="operations@apex.com",
            contact_phone="+91-44-2821-9000",
            created_at=now - timedelta(days=200)
        )
        db.add(customer)
        db.flush()

        # 2. Sites (Chennai Industrial Corridor)
        # Site A: Ambattur Industrial Estate
        site_a = Site(
            customer_id=customer.id,
            code="SITE-A",
            name="Apex Plant 1 (Ambattur)",
            lat=13.0827,
            lng=80.1542,
            access_notes="Main Security Gate 3, Heavy Vehicle Bay A. Escort required.",
            safety_requirements="Safety shoes, high-vis jacket, ear protection, and electrical permit.",
            geofence_radius_m=600.0,
            created_at=now - timedelta(days=200)
        )
        # Site B: Sriperumbudur Hub (~32 km away)
        site_b = Site(
            customer_id=customer.id,
            code="SITE-B",
            name="Apex Plant 2 (Sriperumbudur)",
            lat=12.9734,
            lng=79.9482,
            access_notes="Logistics Gate 1, Warehouse loading dock 4.",
            safety_requirements="Steel-toed boots, hard hat.",
            geofence_radius_m=800.0,
            created_at=now - timedelta(days=200)
        )
        # Site C: Guindy Facility (~15 km away)
        site_c = Site(
            customer_id=customer.id,
            code="SITE-C",
            name="Apex R&D / Press Facility (Guindy)",
            lat=13.0067,
            lng=80.2025,
            access_notes="Facility entrance B, cleanroom footwear required in Bay 2.",
            safety_requirements="Anti-static wristband, safety glasses.",
            geofence_radius_m=500.0,
            created_at=now - timedelta(days=200)
        )
        db.add_all([site_a, site_b, site_c])
        db.flush()

        # 3. Machines (10 industrial machines including M-104)
        machines = []
        # Machine M-104: Heavy Hydraulic Press at Site A
        m104 = Machine(
            site_id=site_a.id,
            code="M-104",
            model="HydraPress HP-500",
            serial="SN-HP500-2023-0104",
            criticality="CRITICAL",
            status="OPERATIONAL",
            warranty_until=now + timedelta(days=180),
            contract_active=True,
            qr_token="qr_m104_token_apex_plant1",
            installed_on=now - timedelta(days=400),
            health_score=52.0,  # Starting in Watch / At-Risk zone due to chronic repeat bearing failures
            created_at=now - timedelta(days=400)
        )
        machines.append(m104)

        for i in range(101, 110):
            if i == 104:
                continue
            site_target = site_a if i % 3 == 0 else (site_b if i % 3 == 1 else site_c)
            crit = "HIGH" if i % 2 == 0 else "MEDIUM"
            mach = Machine(
                site_id=site_target.id,
                code=f"M-{i}",
                model="HydraPress HP-500" if i % 2 == 0 else "VibroMill VM-300",
                serial=f"SN-IND-{i}-2023",
                criticality=crit,
                status="OPERATIONAL",
                warranty_until=now + timedelta(days=365),
                contract_active=True,
                qr_token=f"qr_m{i}_token_apex",
                installed_on=now - timedelta(days=300),
                health_score=94.0,
                created_at=now - timedelta(days=300)
            )
            machines.append(mach)

        db.add_all(machines)
        db.flush()

        # 4. Users (Demo Accounts)
        users = [
            User(
                email="admin@sentinelops.com",
                name="Vikram Seth (Admin)",
                role="ADMIN",
                hashed_password=get_password_hash("admin123"),
                telegram_chat_id="demo_admin_tg"
            ),
            User(
                email="manager@sentinelops.com",
                name="Ananya Sharma (Dispatcher)",
                role="MANAGER",
                hashed_password=get_password_hash("manager123"),
                telegram_chat_id="demo_manager_tg"
            ),
            User(
                email="supervisor@sentinelops.com",
                name="Karthik Raja (Supervisor)",
                role="SUPERVISOR",
                hashed_password=get_password_hash("supervisor123"),
                telegram_chat_id="demo_sup_tg"
            ),
            User(
                email="tech07@sentinelops.com",
                name="Rahul Sharma (Senior Tech)",
                role="TECHNICIAN",
                hashed_password=get_password_hash("tech123"),
                telegram_chat_id="demo_tech7_tg"
            ),
            User(
                email="customer@apex.com",
                name="Suresh Nair (Apex Operations)",
                role="CUSTOMER",
                customer_id=customer.id,
                hashed_password=get_password_hash("customer123")
            )
        ]
        db.add_all(users)
        db.flush()

        # 5. Skills
        skills = [
            Skill(code="SKILL-HYD", name="Hydraulics & High Pressure Systems", category="Mechanical"),
            Skill(code="SKILL-ELEC", name="Electrical & Drives", category="Electrical"),
            Skill(code="SKILL-PLC", name="PLC & Automation Diagnostics", category="Controls"),
            Skill(code="SKILL-MECH", name="Heavy Machinery Mechanical Repair", category="Mechanical"),
            Skill(code="SKILL-VIB", name="Vibration Analysis & Precision Alignment", category="Diagnostics"),
        ]
        db.add_all(skills)
        db.flush()

        # 6. Technicians (T-01 to T-10)
        # T-07 is Rahul (top match for M-104)
        tech_users = []
        for i in range(1, 11):
            t_code = f"T-{i:02d}"
            if i == 7:
                # Rahul
                u = users[3]  # tech07
            else:
                u = User(
                    email=f"tech{i:02d}@sentinelops.com",
                    name=f"Field Tech {t_code}",
                    role="TECHNICIAN",
                    hashed_password=get_password_hash("tech123")
                )
                db.add(u)
                db.flush()
            tech_users.append((t_code, u))

        tech_entities = []
        for t_code, u in tech_users:
            if t_code == "T-07":
                # Rahul: Near Site A (13.0850, 80.1600), high rating, HydraPress certified
                tech = Technician(
                    user_id=u.id,
                    code=t_code,
                    base_lat=13.0850,
                    base_lng=80.1600,
                    current_lat=13.0850,
                    current_lng=80.1600,
                    status="AVAILABLE",
                    max_daily_jobs=5,
                    hourly_rate=65.0,
                    rating=4.9,
                    last_checkin=now
                )
            elif t_code == "T-02":
                # Backup tech: Near Site A, slightly lower rating
                tech = Technician(
                    user_id=u.id,
                    code=t_code,
                    base_lat=13.0910,
                    base_lng=80.1450,
                    current_lat=13.0910,
                    current_lng=80.1450,
                    status="AVAILABLE",
                    max_daily_jobs=4,
                    hourly_rate=55.0,
                    rating=4.7,
                    last_checkin=now
                )
            elif t_code == "T-05":
                # Tech in Sriperumbudur
                tech = Technician(
                    user_id=u.id,
                    code=t_code,
                    base_lat=12.9800,
                    base_lng=79.9500,
                    current_lat=12.9800,
                    current_lng=79.9500,
                    status="AVAILABLE",
                    max_daily_jobs=5,
                    hourly_rate=60.0,
                    rating=4.8,
                    last_checkin=now
                )
            else:
                tech = Technician(
                    user_id=u.id,
                    code=t_code,
                    base_lat=13.0400 + (len(tech_entities) * 0.01),
                    base_lng=80.1800 + (len(tech_entities) * 0.01),
                    current_lat=13.0400 + (len(tech_entities) * 0.01),
                    current_lng=80.1800 + (len(tech_entities) * 0.01),
                    status="AVAILABLE" if len(tech_entities) % 2 == 0 else "BUSY",
                    max_daily_jobs=4,
                    hourly_rate=50.0,
                    rating=4.5 + (len(tech_entities) * 0.04),
                    last_checkin=now
                )
            db.add(tech)
            tech_entities.append(tech)

        db.flush()

        # Assign skills & certifications
        # T-07 (Rahul) has Hydraulics lvl 5, Mechanical lvl 5, Vibration lvl 4, and HydraPress HP-500 Cert
        t07 = next(t for t in tech_entities if t.code == "T-07")
        db.add(TechnicianSkill(technician_id=t07.id, skill_id=skills[0].id, level=5))
        db.add(TechnicianSkill(technician_id=t07.id, skill_id=skills[3].id, level=5))
        db.add(TechnicianSkill(technician_id=t07.id, skill_id=skills[4].id, level=4))
        db.add(TechnicianCertification(technician_id=t07.id, machine_model="HydraPress HP-500", expires_at=now + timedelta(days=365)))

        # T-02 (Backup) has Hydraulics lvl 4, Mechanical lvl 4, and HydraPress cert
        t02 = next(t for t in tech_entities if t.code == "T-02")
        db.add(TechnicianSkill(technician_id=t02.id, skill_id=skills[0].id, level=4))
        db.add(TechnicianSkill(technician_id=t02.id, skill_id=skills[3].id, level=4))
        db.add(TechnicianCertification(technician_id=t02.id, machine_model="HydraPress HP-500", expires_at=now + timedelta(days=180)))

        # T-05 has skills
        t05 = next(t for t in tech_entities if t.code == "T-05")
        db.add(TechnicianSkill(technician_id=t05.id, skill_id=skills[0].id, level=4))
        db.add(TechnicianSkill(technician_id=t05.id, skill_id=skills[1].id, level=4))

        # Give all techs basic mechanical skill
        for t in tech_entities:
            if t.code not in ("T-07", "T-02", "T-05"):
                db.add(TechnicianSkill(technician_id=t.id, skill_id=skills[3].id, level=3))

        db.flush()

        # 7. Inventory Items (~20 parts, tools, consumables)
        # Bearing X is key: SKU-BRG-X
        bearing_x = InventoryItem(
            sku="SKU-BRG-X",
            name="Heavy Roller Bearing X-200",
            kind="PART",
            unit_cost=320.0,
            compat_group="BRG-GROUP-A"
        )
        # Compatible substitute: SKU-BRG-X-PLUS
        bearing_x_sub = InventoryItem(
            sku="SKU-BRG-X-PLUS",
            name="Reinforced Spherical Bearing X-Pro",
            kind="PART",
            unit_cost=380.0,
            compat_group="BRG-GROUP-A"
        )
        seal_kit = InventoryItem(
            sku="SKU-SEAL-HYD",
            name="High-Pressure Viton Seal Kit 500",
            kind="PART",
            unit_cost=95.0,
            compat_group="SEAL-500"
        )
        hyd_oil = InventoryItem(
            sku="SKU-OIL-ISO46",
            name="Hydraulic Fluid ISO VG 46 (20L)",
            kind="CONSUMABLE",
            unit_cost=75.0,
            compat_group=None
        )
        bearing_puller = InventoryItem(
            sku="SKU-TOOL-PULL",
            name="Hydraulic Bearing Puller Set 10T",
            kind="TOOL",
            unit_cost=450.0,
            compat_group=None
        )
        laser_align = InventoryItem(
            sku="SKU-TOOL-LASER",
            name="Precision Shaft Alignment Kit",
            kind="TOOL",
            unit_cost=900.0,
            compat_group=None
        )
        pressure_gauge = InventoryItem(
            sku="SKU-TOOL-GAUGE",
            name="Digital Pressure Test Manifold 600 Bar",
            kind="TOOL",
            unit_cost=210.0,
            compat_group=None
        )

        other_items = [
            InventoryItem(sku=f"SKU-ELEC-{i}", name=f"Siemens Sensor/Module Type {i}", kind="PART", unit_cost=150.0 + i * 20)
            for i in range(1, 14)
        ]

        all_inv = [bearing_x, bearing_x_sub, seal_kit, hyd_oil, bearing_puller, laser_align, pressure_gauge] + other_items
        db.add_all(all_inv)
        db.flush()

        # 8. Stock Levels
        # Scenario Requirement: Bearing X has 0 on hand at Site A, and 5 at Site B!
        db.add(StockLevel(item_id=bearing_x.id, location_type="SITE", location_id=site_a.id, on_hand=0, reserved=0, min_level=2))
        db.add(StockLevel(item_id=bearing_x.id, location_type="SITE", location_id=site_b.id, on_hand=5, reserved=0, min_level=2))
        db.add(StockLevel(item_id=bearing_x.id, location_type="SITE", location_id=site_c.id, on_hand=1, reserved=0, min_level=1))
        db.add(StockLevel(item_id=bearing_x.id, location_type="WAREHOUSE", location_id=0, on_hand=10, reserved=0, min_level=5))

        # Substitute Bearing X-Pro: 1 on hand at Site A
        db.add(StockLevel(item_id=bearing_x_sub.id, location_type="SITE", location_id=site_a.id, on_hand=0, reserved=0, min_level=1))
        db.add(StockLevel(item_id=bearing_x_sub.id, location_type="SITE", location_id=site_b.id, on_hand=2, reserved=0, min_level=1))

        # Van stock for T-02 carries a bearing
        db.add(StockLevel(item_id=bearing_x.id, location_type="VAN", location_id=t02.id, on_hand=1, reserved=0, min_level=1))

        # Consumables and tools available at Site A
        for itm in [seal_kit, hyd_oil, bearing_puller, laser_align, pressure_gauge]:
            db.add(StockLevel(item_id=itm.id, location_type="SITE", location_id=site_a.id, on_hand=4, reserved=0, min_level=2))
            db.add(StockLevel(item_id=itm.id, location_type="SITE", location_id=site_b.id, on_hand=6, reserved=0, min_level=2))

        db.flush()

        # 9. Fault Categories (6 categories)
        # Category 1: Bearing Failure (Triggers Bearing X shortage)
        cat_bearing = FaultCategory(
            code="CAT-BRG",
            name="Bearing Failure / Spindle Seizure",
            description="Bearing vibration or mechanical seizure requiring roller bearing replacement and alignment.",
            expected_duration_h=3.0,
            priority_boost=1,
            requires_certification=True
        )
        cat_hyd = FaultCategory(
            code="CAT-HYD",
            name="Hydraulic System Leak / Pressure Loss",
            description="Severe hydraulic fluid leak or cylinder seal failure requiring seal replacement and pressure test.",
            expected_duration_h=2.5,
            priority_boost=1,
            requires_certification=True
        )
        cat_elec = FaultCategory(
            code="CAT-ELEC",
            name="Electrical Drive / Motor Fault",
            description="Variable frequency drive tripping, power stage fault, or blown contactor.",
            expected_duration_h=2.0,
            priority_boost=0,
            requires_certification=False
        )
        cat_plc = FaultCategory(
            code="CAT-PLC",
            name="PLC & Controller Communication Failure",
            description="Profibus / Profinet bus fault, I/O module timeout, or ladder logic halt.",
            expected_duration_h=2.0,
            priority_boost=0,
            requires_certification=False
        )
        cat_vib = FaultCategory(
            code="CAT-VIB",
            name="Unbalance & Excessive Vibration",
            description="Unusual vibration exceeding ISO vibration limits; requires balancing and torque audit.",
            expected_duration_h=2.0,
            priority_boost=0,
            requires_certification=False
        )
        cat_calib = FaultCategory(
            code="CAT-CALIB",
            name="Precision Calibration & Inspection",
            description="Periodic calibration of pressure sensors, safety interlocks, and travel encoders.",
            expected_duration_h=1.5,
            priority_boost=0,
            requires_certification=False
        )
        db.add_all([cat_bearing, cat_hyd, cat_elec, cat_plc, cat_vib, cat_calib])
        db.flush()

        # Category Skills
        db.add(FaultCategorySkill(fault_category_id=cat_bearing.id, skill_id=skills[0].id, min_level=4))
        db.add(FaultCategorySkill(fault_category_id=cat_bearing.id, skill_id=skills[3].id, min_level=4))
        db.add(FaultCategorySkill(fault_category_id=cat_hyd.id, skill_id=skills[0].id, min_level=4))
        db.add(FaultCategorySkill(fault_category_id=cat_elec.id, skill_id=skills[1].id, min_level=3))
        db.add(FaultCategorySkill(fault_category_id=cat_plc.id, skill_id=skills[2].id, min_level=3))

        # Service Kits
        # Kit for Bearing Failure: Bearing X, Bearing Puller, Shaft Laser Alignment, ISO 46 Oil
        db.add(KitItem(fault_category_id=cat_bearing.id, item_id=bearing_x.id, kind="PART", qty=1))
        db.add(KitItem(fault_category_id=cat_bearing.id, item_id=bearing_puller.id, kind="TOOL", qty=1))
        db.add(KitItem(fault_category_id=cat_bearing.id, item_id=laser_align.id, kind="TOOL", qty=1))
        db.add(KitItem(fault_category_id=cat_bearing.id, item_id=hyd_oil.id, kind="CONSUMABLE", qty=1))

        # Kit for Hydraulic Leak
        db.add(KitItem(fault_category_id=cat_hyd.id, item_id=seal_kit.id, kind="PART", qty=1))
        db.add(KitItem(fault_category_id=cat_hyd.id, item_id=hyd_oil.id, kind="CONSUMABLE", qty=2))
        db.add(KitItem(fault_category_id=cat_hyd.id, item_id=pressure_gauge.id, kind="TOOL", qty=1))

        # Evidence Template Items for Bearing Failure
        evidence_templates = [
            EvidenceTemplateItem(fault_category_id=cat_bearing.id, key="before_photo", label="Damaged Bearing Disassembly Photo", type="PHOTO", mandatory=True, who_submits="TECHNICIAN"),
            EvidenceTemplateItem(fault_category_id=cat_bearing.id, key="serial_check", label="Replacement Bearing Serial Verification", type="SERIAL", mandatory=True, who_submits="TECHNICIAN"),
            EvidenceTemplateItem(fault_category_id=cat_bearing.id, key="after_photo", label="Installed Bearing & Clean Assembly Photo", type="PHOTO", mandatory=True, who_submits="TECHNICIAN"),
            EvidenceTemplateItem(fault_category_id=cat_bearing.id, key="checklist", label="Shaft Alignment & Torque Checklist", type="CHECKLIST", mandatory=True, who_submits="TECHNICIAN"),
            EvidenceTemplateItem(fault_category_id=cat_bearing.id, key="test_run", label="Post-Repair Vibration Spectrum Test (<2.8 mm/s)", type="TEST_RESULT", mandatory=True, who_submits="TECHNICIAN"),
            EvidenceTemplateItem(fault_category_id=cat_bearing.id, key="customer_signoff", label="Plant Operations Supervisor Sign-Off", type="SIGN_OFF", mandatory=True, who_submits="CUSTOMER"),
            EvidenceTemplateItem(fault_category_id=cat_bearing.id, key="supervisor_approval", label="Field Service Engineering Final Verification", type="SIGN_OFF", mandatory=True, who_submits="SUPERVISOR"),
        ]
        db.add_all(evidence_templates)
        db.flush()

        # 10. Exception Rules Preloaded
        rules = [
            ExceptionRule(
                code="ACK_TIMEOUT",
                name="Technician Acknowledgement Timeout",
                enabled=True,
                params=json.dumps({"timeout_minutes": 15}),
                actions=json.dumps(["notify_dispatcher", "recommend_backup", "raise_flag"]),
                escalate_to_role="MANAGER"
            ),
            ExceptionRule(
                code="TECH_DECLINE",
                name="Technician Declined Assignment",
                enabled=True,
                params=json.dumps({}),
                actions=json.dumps(["release_reservations", "trigger_hotswap_recommendation"]),
                escalate_to_role="MANAGER"
            ),
            ExceptionRule(
                code="TECH_NO_SHOW",
                name="Technician No-Show at Site",
                enabled=True,
                params=json.dumps({"grace_minutes": 15}),
                actions=json.dumps(["mark_no_show", "escalate_to_supervisor", "hot_swap"]),
                escalate_to_role="MANAGER"
            ),
            ExceptionRule(
                code="PART_SHORTAGE",
                name="Critical Service Kit Stock Shortage",
                enabled=True,
                params=json.dumps({}),
                actions=json.dumps(["block_dispatch", "run_impact_chain", "suggest_transfer_or_sub"]),
                escalate_to_role="MANAGER"
            ),
            ExceptionRule(
                code="SLA_BREACH",
                name="Contracted SLA Window Exceeded",
                enabled=True,
                params=json.dumps({}),
                actions=json.dumps(["notify_admin", "record_audit_event", "dispatch_supervisory_lead"]),
                escalate_to_role="ADMIN"
            ),
            ExceptionRule(
                code="STUCK_IN_PROGRESS",
                name="Execution Time Exceeds 1.5x Estimated Duration",
                enabled=True,
                params=json.dumps({"multiplier": 1.5}),
                actions=json.dumps(["notify_supervisor", "request_status_update"]),
                escalate_to_role="SUPERVISOR"
            ),
            ExceptionRule(
                code="REPEAT_FAILURE",
                name="Chronic Repeat Component Failure Detection (>=3 in 90d)",
                enabled=True,
                params=json.dumps({"threshold": 3, "window_days": 90}),
                actions=json.dumps(["prompt_failure_prevention_loop", "bump_min_stock"]),
                escalate_to_role="MANAGER"
            )
        ]
        db.add_all(rules)
        db.flush()

        # 11. Populate M-104 Historical Service Records (4 past bearing failures in 6 months)
        # Sets up day-one MTBF, repeat failure detection, and health score!
        history_dates = [
            now - timedelta(days=120),
            now - timedelta(days=75),
            now - timedelta(days=40),
            now - timedelta(days=10)
        ]

        for idx, h_date in enumerate(history_dates, 1):
            req_code = f"SR-104-HIST-{idx}"
            hist_req = ServiceRequest(
                code=req_code,
                machine_id=m104.id,
                site_id=site_a.id,
                raised_by=users[4].id,  # Suresh (Customer)
                source="WEB",
                fault_category_id=cat_bearing.id,
                description=f"Historical Bearing Failure #{idx}: Main spindle bearing overheat and excessive vibration on M-104.",
                priority="HIGH",
                effective_priority="CRITICAL",
                status="VERIFIED",
                expected_duration_h=3.0,
                readiness_score=100.0,
                risk_ratio=0.65,
                risk_level="SAFE",
                safety_confirmed=True,
                track_token=uuid.uuid4().hex,
                created_at=h_date,
                validated_at=h_date + timedelta(minutes=5),
                approved_at=h_date + timedelta(minutes=10),
                assigned_at=h_date + timedelta(minutes=15),
                started_at=h_date + timedelta(minutes=45),
                completed_at=h_date + timedelta(hours=3, minutes=15),
                verified_at=h_date + timedelta(hours=3, minutes=45)
            )
            db.add(hist_req)
            db.flush()

            # Assignment by Rahul (T-07)
            hist_asg = Assignment(
                request_id=hist_req.id,
                technician_id=t07.id,
                plan_type="BEST_FIT",
                match_score=96.5,
                score_breakdown=json.dumps({"skill": 98, "distance": 95, "machine": 100}),
                explanation="T-07 selected: certified for HydraPress HP-500 with top diagnostic track record.",
                eta_minutes=25.0,
                status="COMPLETED",
                acknowledged_at=h_date + timedelta(minutes=20),
                created_at=h_date + timedelta(minutes=15)
            )
            db.add(hist_asg)

            # Reservation
            hist_res = Reservation(
                request_id=hist_req.id,
                item_id=bearing_x.id,
                qty=1,
                source_location="Apex Plant 1",
                source_type="SITE",
                source_location_id=site_a.id,
                status="ISSUED",
                created_at=h_date
            )
            db.add(hist_res)

            # Mandatory Evidence Items
            for tmpl in evidence_templates:
                db.add(EvidenceItem(
                    request_id=hist_req.id,
                    template_key=tmpl.key,
                    type=tmpl.type,
                    file_url="/uploads/demo_bearing_proof.jpg" if tmpl.type == "PHOTO" else None,
                    text_value=f"Verified check for {tmpl.label}" if tmpl.type != "PHOTO" else None,
                    submitted_by=t07.user_id,
                    lat=13.0827,
                    lng=80.1542,
                    presence_status="VERIFIED",
                    status="ACCEPTED",
                    captured_at=h_date + timedelta(hours=2)
                ))

        db.flush()

        # 12. Live demo operations: keep the Control Tower useful on first launch.
        # These records are local demo data and do not require Supabase, Neon, Telegram, or an LLM key.
        live_in_progress = ServiceRequest(
            code="SR-M104-LIVE", machine_id=m104.id, site_id=site_a.id, raised_by=users[1].id,
            source="IOT", fault_category_id=cat_bearing.id,
            description="Live M-104 bearing vibration alert requiring field inspection and alignment.",
            priority="CRITICAL", effective_priority="CRITICAL", status="IN_PROGRESS",
            expected_duration_h=3.0, readiness_score=96.0, risk_ratio=0.72, risk_level="AT_RISK",
            safety_confirmed=True, track_token=uuid.uuid4().hex,
            created_at=now - timedelta(hours=1, minutes=10), validated_at=now - timedelta(hours=1),
            approved_at=now - timedelta(minutes=55), assigned_at=now - timedelta(minutes=45),
            started_at=now - timedelta(minutes=25), sla_due_at=now + timedelta(hours=1, minutes=50),
            response_due_at=now - timedelta(minutes=40)
        )
        db.add(live_in_progress); db.flush()
        db.add(Assignment(
            request_id=live_in_progress.id, technician_id=t07.id, plan_type="BEST_FIT",
            match_score=96.5, score_breakdown=json.dumps({"skill":98,"distance":95,"machine":100}),
            explanation="T-07 selected for HydraPress certification, vibration skill and proximity.",
            eta_minutes=0, status="IN_PROGRESS", acknowledged_at=now - timedelta(minutes=40),
            ack_due_at=now - timedelta(minutes=50), created_at=now - timedelta(minutes=45)
        ))

        live_assigned = ServiceRequest(
            code="SR-M102-READY", machine_id=machines[1].id, site_id=machines[1].site_id, raised_by=users[2].id,
            source="WEB", fault_category_id=cat_hyd.id,
            description="Hydraulic pressure loss inspection; dispatch kit prepared.",
            priority="HIGH", effective_priority="HIGH", status="ASSIGNED", expected_duration_h=2.5,
            readiness_score=91.0, risk_ratio=0.45, risk_level="SAFE", safety_confirmed=False,
            track_token=uuid.uuid4().hex, created_at=now - timedelta(minutes=35),
            validated_at=now - timedelta(minutes=30), approved_at=now - timedelta(minutes=25),
            assigned_at=now - timedelta(minutes=20), sla_due_at=now + timedelta(hours=3),
            response_due_at=now - timedelta(minutes=10)
        )
        db.add(live_assigned); db.flush()
        db.add(Assignment(
            request_id=live_assigned.id, technician_id=t02.id, plan_type="FASTEST",
            match_score=91.0, score_breakdown=json.dumps({"skill":94,"distance":90,"machine":89}),
            explanation="T-02 selected as nearby certified backup.", eta_minutes=18, status="ASSIGNED",
            ack_due_at=now + timedelta(minutes=5), created_at=now - timedelta(minutes=20)
        ))

        live_exception = ServiceRequest(
            code="SR-M105-EXC", machine_id=machines[4].id, site_id=machines[4].site_id, raised_by=users[1].id,
            source="WEB", fault_category_id=cat_bearing.id,
            description="Bearing replacement blocked by technician dropout; rescue plan required.",
            priority="HIGH", effective_priority="CRITICAL", status="EXCEPTION", expected_duration_h=3.0,
            readiness_score=74.0, risk_ratio=0.88, risk_level="CRITICAL", safety_confirmed=False,
            track_token=uuid.uuid4().hex, created_at=now - timedelta(minutes=50),
            validated_at=now - timedelta(minutes=45), approved_at=now - timedelta(minutes=40),
            assigned_at=now - timedelta(minutes=35), sla_due_at=now + timedelta(minutes=50),
            response_due_at=now - timedelta(minutes=20)
        )
        db.add(live_exception); db.flush()
        db.add(Assignment(
            request_id=live_exception.id, technician_id=t07.id, plan_type="BEST_FIT", match_score=96.5,
            score_breakdown=json.dumps({"skill":98,"distance":95,"machine":100}),
            explanation="Original dispatch before technician dropout.", eta_minutes=20, status="DECLINED",
            ack_due_at=now - timedelta(minutes=20), created_at=now - timedelta(minutes=35),
            replaced_reason="[DEMO] Technician unavailable after dispatch"
        ))
        db.add(ExceptionFlag(
            request_id=live_exception.id, rule_code="TECH_DECLINE", severity="CRITICAL",
            reason="[DEMO] Assigned technician became unavailable after dispatch.",
            blocker="Technician dropout", recommended_action="Execute Hot-Swap to T-02 or another qualified candidate.",
            owner_role="MANAGER", status="OPEN", options_snapshot=json.dumps([{"technician_id": t02.id, "technician_code": "T-02", "plan_type": "HOT_SWAP", "match_score": 91.0, "eta_minutes": 18, "projected_sla": "AT_RISK"}]), created_at=now - timedelta(minutes=18)
        ))

        live_verify = ServiceRequest(
            code="SR-M108-VERIFY", machine_id=machines[7].id, site_id=machines[7].site_id, raised_by=users[2].id,
            source="WEB", fault_category_id=cat_vib.id, description="Vibration repair completed; supervisor verification pending.",
            priority="MEDIUM", effective_priority="MEDIUM", status="COMPLETED", expected_duration_h=2.0,
            readiness_score=100.0, risk_ratio=0.18, risk_level="SAFE", safety_confirmed=True,
            track_token=uuid.uuid4().hex, created_at=now - timedelta(hours=2),
            validated_at=now - timedelta(hours=1, minutes=50), approved_at=now - timedelta(hours=1, minutes=40),
            assigned_at=now - timedelta(hours=1, minutes=30), started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(minutes=15), sla_due_at=now + timedelta(hours=2),
            response_due_at=now - timedelta(hours=1, minutes=20)
        )
        db.add(live_verify); db.flush()
        db.add(Assignment(
            request_id=live_verify.id, technician_id=t05.id, plan_type="BEST_FIT", match_score=89.0,
            score_breakdown=json.dumps({"skill":90,"distance":88,"machine":89}), explanation="T-05 completed vibration inspection.",
            eta_minutes=0, status="COMPLETED", acknowledged_at=now - timedelta(hours=1, minutes=25), created_at=now - timedelta(hours=1, minutes=30)
        ))
        db.add(ExceptionFlag(
            request_id=live_verify.id, rule_code="STUCK_IN_PROGRESS", severity="WARNING",
            reason="Verification queue requires supervisor review of completed field evidence.",
            blocker="Pending supervisor verification", recommended_action="Review evidence and verify completion.",
            owner_role="SUPERVISOR", status="OPEN", options_snapshot=json.dumps([]), created_at=now - timedelta(minutes=10)
        ))

        db.flush()

        # Seed initial audit log genesis entry
        append_audit_log(
            db=db,
            entity_type="System",
            entity_id=1,
            action="SYSTEM_INITIALIZED",
            actor_id=users[0].id,
            actor_role="ADMIN",
            meta={"note": "SentinelOps Genesis Hash Block Created with demo dataset"}
        )

        db.commit()
        print("SentinelOps database seeding completed successfully.")

    except Exception as e:
        db.rollback()
        print(f"Error during seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    is_reset = "--reset" in sys.argv
    seed_database(reset=is_reset)
