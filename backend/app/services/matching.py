"""Explainable Matching Engine and 3-Plan Builder for SentinelOps."""
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.models import (
    Technician, ServiceRequest, Machine, Site, FaultCategory,
    TechnicianSkill, TechnicianCertification, Assignment, StockLevel
)
from app.plugins.distance import haversine_km, calculate_travel_minutes
from app.core.time import utcnow


def calculate_match_score(
    db: Session,
    tech: Technician,
    request: ServiceRequest,
    exclude_tech_ids: Optional[List[int]] = None
) -> Tuple[bool, float, Dict[str, Any], str]:
    """Evaluate hard filters and compute weighted 0-100 MatchScore.
    Returns: (is_eligible, score, breakdown_dict, explanation_text)
    """
    if exclude_tech_ids and tech.id in exclude_tech_ids:
        return False, 0.0, {}, "Excluded by parameter"

    # --- 1. HARD FILTERS ---
    # A. Duty status
    if tech.status in ("OFF_DUTY", "UNAVAILABLE"):
        return False, 0.0, {}, f"Technician is currently {tech.status}"

    # B. Skill Requirements
    tech_skills = {ts.skill_id: ts.level for ts in tech.skills}
    for req_skill in request.fault_category.required_skills:
        tech_level = tech_skills.get(req_skill.skill_id, 0)
        if tech_level < req_skill.min_level:
            return False, 0.0, {}, f"Lacks minimum level {req_skill.min_level} for {req_skill.skill.name}"

    # C. Burnout Filter: Daily Job Count
    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_jobs = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.created_at >= today_start,
            Assignment.status.in_(["ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS", "COMPLETED"])
        )
        .count()
    )
    if today_jobs >= tech.max_daily_jobs:
        return False, 0.0, {}, f"Burnout filter: Reached max daily jobs ({today_jobs}/{tech.max_daily_jobs})"

    # --- 2. WEIGHTED SCORING (0 to 100) ---
    site = request.site
    machine = request.machine

    # Factor 1: Skill Match (30%)
    # Average excess skill level
    excess_levels = []
    for req_skill in request.fault_category.required_skills:
        tech_level = tech_skills.get(req_skill.skill_id, 1)
        # Scale 1-5 to a 60-100 score
        excess_levels.append(min(100.0, 60.0 + (tech_level * 8.0)))
    skill_score = sum(excess_levels) / len(excess_levels) if excess_levels else 80.0

    # Factor 2: Availability (20%)
    if tech.status == "AVAILABLE":
        avail_score = 100.0
    elif tech.status == "BUSY":
        avail_score = 60.0
    else:
        avail_score = 20.0

    # Factor 3: Distance and ETA (20%)
    # Use current lat/lng or base
    t_lat = tech.current_lat or tech.base_lat
    t_lng = tech.current_lng or tech.base_lng
    dist_km = haversine_km(t_lat, t_lng, site.lat, site.lng)
    eta_mins = calculate_travel_minutes(dist_km)
    # Closer is higher: 0km=100, 50km=50, 100km+=10
    dist_score = max(10.0, min(100.0, 100.0 - (dist_km * 0.9)))

    # Factor 4: Machine Familiarity (15%)
    # A. Certification for model
    has_cert = any(c.machine_model == machine.model for c in tech.certifications)
    # B. Prior jobs on exact machine
    prior_jobs = (
        db.query(Assignment)
        .join(ServiceRequest)
        .filter(
            Assignment.technician_id == tech.id,
            ServiceRequest.machine_id == machine.id,
            Assignment.status == "COMPLETED"
        )
        .count()
    )
    familiarity_score = (50.0 if has_cert else 10.0) + min(50.0, prior_jobs * 25.0)

    # Factor 5: Workload Balance (10%)
    remaining_capacity = max(0, tech.max_daily_jobs - today_jobs)
    workload_score = min(100.0, (remaining_capacity / float(tech.max_daily_jobs)) * 100.0)

    # Factor 6: Track Record (5%)
    # Rating out of 5 -> scale to 100
    track_record_score = min(100.0, (tech.rating / 5.0) * 100.0)

    total_score = round(
        (skill_score * 0.30)
        + (avail_score * 0.20)
        + (dist_score * 0.20)
        + (familiarity_score * 0.15)
        + (workload_score * 0.10)
        + (track_record_score * 0.05),
        1
    )

    breakdown = {
        "skill_match": round(skill_score, 1),
        "availability": round(avail_score, 1),
        "distance_and_eta": round(dist_score, 1),
        "machine_familiarity": round(familiarity_score, 1),
        "workload_balance": round(workload_score, 1),
        "track_record": round(track_record_score, 1),
        "distance_km": dist_km,
        "eta_minutes": eta_mins,
        "today_jobs": today_jobs,
        "has_certification": has_cert,
        "prior_jobs_on_machine": prior_jobs
    }

    # Generate explainable "why this technician" text
    explanation_parts = [f"{tech.code} ({tech.user.name})"]
    if has_cert:
        explanation_parts.append(f"holds {machine.model} certification")
    if prior_jobs > 0:
        explanation_parts.append(f"previously serviced this machine {prior_jobs} time(s)")
    if dist_km < 15.0:
        explanation_parts.append(f"is nearby (~{int(eta_mins)}m ETA, {dist_km} km)")
    else:
        explanation_parts.append(f"ETA ~{int(eta_mins)}m")
    if tech.rating >= 4.8:
        explanation_parts.append(f"{tech.rating}★ rating")

    explanation = "; ".join(explanation_parts) + "."

    return True, total_score, breakdown, explanation


def build_3_plans(
    db: Session,
    request: ServiceRequest,
    exclude_tech_ids: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """Build up to 3 distinct explainable dispatch plans:
    1. Fastest: Earliest projected finish time.
    2. Best Fit: Highest overall match score.
    3. Least Disruptive: Lowest current workload and lowest operational friction.
    """
    technicians = db.query(Technician).all()
    candidates = []

    validation_data = json.loads(request.validation_report) if request.validation_report else {}
    shortage_items = validation_data.get("service_kit", {}).get("shortage_items", [])
    
    # Part arrival delay
    part_transit_minutes = 0.0
    part_source_label = "Site Local Stock"
    if shortage_items:
        transfers = shortage_items[0].get("transfer_options", [])
        if transfers:
            part_transit_minutes = transfers[0].get("eta_minutes", 40.0)
            part_source_label = f"Inter-Site Transfer ({transfers[0]['site_name']})"
        else:
            part_source_label = "Central Warehouse / Expedited"
            part_transit_minutes = 120.0

    duration_h = request.expected_duration_h or 2.0
    sla_due = request.sla_due_at or (utcnow() + timedelta(hours=24))

    for tech in technicians:
        is_eligible, score, breakdown, explanation = calculate_match_score(
            db, tech, request, exclude_tech_ids
        )
        if not is_eligible:
            continue

        eta_mins = breakdown["eta_minutes"]
        
        # Check if tech has part in van
        van_has_part = False
        if shortage_items:
            tech_van_stock = (
                db.query(StockLevel)
                .filter(
                    StockLevel.item_id == shortage_items[0]["item_id"],
                    StockLevel.location_type == "VAN",
                    StockLevel.location_id == tech.id,
                    StockLevel.on_hand > 0
                )
                .first()
            )
            if tech_van_stock:
                van_has_part = True
                tech_part_source = f"Van Stock ({tech.code})"
                tech_part_delay = 0.0
            else:
                tech_part_source = part_source_label
                tech_part_delay = part_transit_minutes
        else:
            tech_part_source = part_source_label
            tech_part_delay = 0.0

        # Completion estimate: max(tech_arrival, part_arrival) + duration
        work_start_delay_mins = max(eta_mins, tech_part_delay)
        total_finish_mins = work_start_delay_mins + (duration_h * 60.0)
        projected_completion = utcnow() + timedelta(minutes=total_finish_mins)

        # SLA outcome
        if projected_completion <= sla_due:
            sla_outcome = "SAFE"
        elif (projected_completion - sla_due).total_seconds() < 3600 * 2:
            sla_outcome = "AT_RISK"
        else:
            sla_outcome = "BREACH"

        # Cost bucket calculation
        cost_value = (tech.hourly_rate * duration_h) + (breakdown["distance_km"] * 1.5)
        if cost_value < 150:
            cost_bucket = "LOW"
        elif cost_value < 280:
            cost_bucket = "MEDIUM"
        else:
            cost_bucket = "HIGH"

        candidates.append({
            "technician": {
                "id": tech.id,
                "code": tech.code,
                "name": tech.user.name,
                "rating": tech.rating,
                "hourly_rate": tech.hourly_rate,
                "current_jobs": breakdown["today_jobs"]
            },
            "score": score,
            "breakdown": breakdown,
            "explanation": explanation,
            "part_source": tech_part_source,
            "eta_minutes": eta_mins,
            "projected_completion": projected_completion.isoformat(),
            "sla_outcome": sla_outcome,
            "cost_bucket": cost_bucket,
            "total_finish_mins": total_finish_mins,
            "today_jobs": breakdown["today_jobs"]
        })

    if not candidates:
        return []

    # 1. Best Fit: Highest Match Score
    
        # ---------------------------------------------------------
    # Build three explainable plans.
    #
    # Prefer three different technicians when enough eligible
    # candidates exist. If fewer than three candidates exist,
    # the remaining plans may reuse the best available candidate.
    # ---------------------------------------------------------

    # 1. BEST FIT
    best_fit = max(
        candidates,
        key=lambda c: c["score"]
    )

    used_tech_ids = {
        best_fit["technician"]["id"]
    }

    # 2. FASTEST
    fastest_candidates = [
        c for c in candidates
        if c["technician"]["id"] not in used_tech_ids
    ]

    if fastest_candidates:
        fastest = min(
            fastest_candidates,
            key=lambda c: c["total_finish_mins"]
        )
    else:
        fastest = min(
            candidates,
            key=lambda c: c["total_finish_mins"]
        )

    used_tech_ids.add(
        fastest["technician"]["id"]
    )

    # 3. LEAST DISRUPTIVE
    least_disruptive_candidates = [
        c for c in candidates
        if c["technician"]["id"] not in used_tech_ids
    ]

    if least_disruptive_candidates:
        least_disruptive = min(
            least_disruptive_candidates,
            key=lambda c: (
                c["today_jobs"],
                -c["score"]
            )
        )
    else:
        least_disruptive = min(
            candidates,
            key=lambda c: (
                c["today_jobs"],
                -c["score"]
            )
        )

    plans = [
        {
            "plan_type": "BEST_FIT",
            "title": "Best Fit",
            "badge": "RECOMMENDED",
            "is_recommended": True,
            **best_fit
        },
        {
            "plan_type": "FASTEST",
            "title": "Fastest Recovery",
            "badge": "EARLIEST COMPLETION",
            "is_recommended": False,
            **fastest
        },
        {
            "plan_type": "LEAST_DISRUPTIVE",
            "title": "Least Disruptive",
            "badge": "LOWEST WORKLOAD",
            "is_recommended": False,
            **least_disruptive
        }
    ]

    return plans
