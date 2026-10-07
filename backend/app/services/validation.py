"""Validation Engine and Readiness Gate for SentinelOps."""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List
from sqlalchemy.orm import Session
from app.db.models import (
    Machine, Site, FaultCategory, ServiceRequest, Assignment, KitItem,
    FaultCategorySkill
)
from app.services.inventory import check_kit_availability, compute_impact_chain
from app.core.time import utcnow

# Default SLA resolution hours by priority
SLA_RESOLUTION_HOURS = {
    "CRITICAL": 8.0,
    "HIGH": 24.0,
    "MEDIUM": 48.0,
    "LOW": 72.0
}

# Default Acknowledgement deadline minutes by priority
SLA_ACK_MINUTES = {
    "CRITICAL": 15,
    "HIGH": 30,
    "MEDIUM": 60,
    "LOW": 120
}

PRIORITY_RANKS = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
RANK_TO_PRIORITY = {1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}


def calculate_effective_priority(
    requested_priority: str,
    machine_criticality: str,
    priority_boost: int
) -> Tuple[str, str]:
    """Calculate effective priority based on customer input, machine criticality, and category boost."""
    initial_rank = PRIORITY_RANKS.get(requested_priority.upper(), 2)
    boost = priority_boost

    reasons = []
    if requested_priority.upper() != "MEDIUM":
        reasons.append(f"Customer reported as {requested_priority}")

    if machine_criticality.upper() == "CRITICAL" and initial_rank < 4:
        boost += 2
        reasons.append(f"Machine {machine_criticality} criticality boost (+2)")
    elif machine_criticality.upper() == "HIGH" and initial_rank < 3:
        boost += 1
        reasons.append(f"Machine {machine_criticality} criticality boost (+1)")

    if priority_boost > 0:
        reasons.append(f"Fault category severity boost (+{priority_boost})")

    final_rank = min(4, max(1, initial_rank + boost))
    effective_prio = RANK_TO_PRIORITY[final_rank]

    if not reasons:
        reasons.append("Standard priority allocation")

    return effective_prio, "; ".join(reasons)


def compute_readiness_gate(
    db: Session,
    request: ServiceRequest,
    validation_report: Dict[str, Any]
) -> Tuple[float, List[str], List[str]]:
    """Compute 8-point readiness gate:
    1. Machine eligible
    2. Skills identified
    3. SLA computed
    4. Kit available or substituted
    5. Site and access complete
    6. Safety requirements recorded
    7. Technician assigned
    8. Technician acknowledged
    """
    passed_items = []
    missing_items = []

    # 1. Machine eligible
    if validation_report.get("machine_eligibility", {}).get("status") == "PASS":
        passed_items.append("Machine eligible")
    else:
        missing_items.append("Machine eligibility criteria")

    # 2. Skills identified
    if validation_report.get("required_skills", {}).get("status") in ("PASS", "WARN"):
        passed_items.append("Skills identified")
    else:
        missing_items.append("Required skills identification")

    # 3. SLA computed
    if request.sla_due_at is not None:
        passed_items.append("SLA computed")
    else:
        missing_items.append("SLA calculation")

    # 4. Kit available or substituted / transfer planned
    kit_info = validation_report.get("service_kit", {})
    if kit_info.get("all_available") or (kit_info.get("shortage_items") and any(s.get("transfer_options") or s.get("substitutes") for s in kit_info.get("shortage_items", []))):
        passed_items.append("Kit available or route identified")
    else:
        missing_items.append("Service kit parts availability")

    # 5. Site & access complete
    if validation_report.get("site", {}).get("status") == "PASS":
        passed_items.append("Site and access complete")
    else:
        missing_items.append("Site access info")

    # 6. Safety requirements recorded
    if request.safety_confirmed or request.site.safety_requirements:
        passed_items.append("Safety requirements recorded")
    else:
        missing_items.append("Safety requirements or permit")

    # 7. Technician assigned
    active_assignment = (
        db.query(Assignment)
        .filter(Assignment.request_id == request.id, Assignment.status != "REPLACED")
        .first()
    )
    if active_assignment:
        passed_items.append("Technician assigned")
    else:
        missing_items.append("Technician assignment")

    # 8. Technician acknowledged
    if active_assignment and active_assignment.status in ("ACKNOWLEDGED", "COMPLETED", "IN_PROGRESS"):
        passed_items.append("Technician acknowledged")
    else:
        missing_items.append("Technician acknowledgement")

    score = round((len(passed_items) / 8.0) * 100.0, 1)
    return score, passed_items, missing_items


def run_full_validation(
    db: Session,
    machine_id: int,
    fault_category_id: int,
    requested_priority: str
) -> Dict[str, Any]:
    """Run comprehensive validation engine on request creation."""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise ValueError(f"Machine ID {machine_id} not found.")

    site = machine.site
    fault_cat = db.query(FaultCategory).filter(FaultCategory.id == fault_category_id).first()
    if not fault_cat:
        raise ValueError(f"FaultCategory ID {fault_category_id} not found.")

    now = utcnow()
    report = {}

    # Check 1: Machine eligibility
    is_warranty_valid = bool(machine.warranty_until and machine.warranty_until >= now)
    is_eligible = machine.contract_active or is_warranty_valid

    if is_eligible:
        report["machine_eligibility"] = {
            "status": "PASS",
            "reason": f"Active contract: {machine.contract_active}; Warranty valid: {is_warranty_valid}"
        }
    else:
        report["machine_eligibility"] = {
            "status": "FAIL",
            "reason": "Machine contract is expired and warranty has ended. Ineligible for unscheduled warranty service."
        }

    # Check 2: Site details
    if site and site.lat and site.lng:
        report["site"] = {
            "status": "PASS",
            "site_code": site.code,
            "site_name": site.name,
            "coordinates": f"{site.lat}, {site.lng}",
            "access_notes": site.access_notes or "Standard facility access.",
            "safety_requirements": site.safety_requirements or "Standard PPE required."
        }
    else:
        report["site"] = {
            "status": "FAIL",
            "reason": "Site coordinates or access notes incomplete."
        }

    # Check 3: Priority calculation
    effective_prio, prio_reason = calculate_effective_priority(
        requested_priority, machine.criticality, fault_cat.priority_boost
    )
    report["priority"] = {
        "status": "PASS",
        "requested": requested_priority,
        "effective": effective_prio,
        "reason": prio_reason
    }

    # Check 4: SLA calculation
    res_hours = SLA_RESOLUTION_HOURS.get(effective_prio, 48.0)
    ack_mins = SLA_ACK_MINUTES.get(effective_prio, 60)
    sla_due = now + timedelta(hours=res_hours)
    ack_due = now + timedelta(minutes=ack_mins)
    report["sla"] = {
        "status": "PASS",
        "effective_priority": effective_prio,
        "resolution_hours": res_hours,
        "ack_minutes": ack_mins,
        "sla_due_at": sla_due.isoformat(),
        "ack_due_at": ack_due.isoformat()
    }

    # Check 5: Required skills & certifications
    skills_list = []
    for fcs in fault_cat.required_skills:
        skills_list.append({
            "skill_id": fcs.skill_id,
            "skill_name": fcs.skill.name,
            "min_level": fcs.min_level
        })
    report["required_skills"] = {
        "status": "PASS",
        "requires_certification": fault_cat.requires_certification,
        "machine_model": machine.model if fault_cat.requires_certification else None,
        "skills": skills_list
    }

    # Check 6: Service kit availability
    kit_check = check_kit_availability(db, site.id, fault_cat.id)
    impact_chain = compute_impact_chain(db, machine, site, effective_prio, kit_check["shortage_items"])
    
    report["service_kit"] = kit_check
    report["impact_chain"] = impact_chain

    return report
