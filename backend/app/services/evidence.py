"""Evidence management, completeness calculation, and Proof of Presence geofence checking."""
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.models import ServiceRequest, EvidenceTemplateItem, EvidenceItem, Site
from app.plugins.distance import haversine_km
from app.core.config import settings
from app.core.time import utcnow


def check_proof_of_presence(
    site: Site,
    submitted_lat: Optional[float],
    submitted_lng: Optional[float]
) -> Tuple[str, Optional[float]]:
    """Compare submission coordinates to site geofence radius.
    Returns: (status: VERIFIED | OUTSIDE_GEOFENCE | NOT_PROVIDED, distance_meters)
    """
    if submitted_lat is None or submitted_lng is None:
        return "NOT_PROVIDED", None

    dist_km = haversine_km(submitted_lat, submitted_lng, site.lat, site.lng)
    dist_m = dist_km * 1000.0

    radius_m = site.geofence_radius_m or settings.GEOFENCE_DEFAULT_M
    if dist_m <= radius_m:
        return "VERIFIED", round(dist_m, 1)
    else:
        return "OUTSIDE_GEOFENCE", round(dist_m, 1)


def calculate_evidence_completeness(
    db: Session,
    request: ServiceRequest
) -> Dict[str, Any]:
    """Calculate submitted vs mandatory templates, listing missing items."""
    templates: List[EvidenceTemplateItem] = (
        db.query(EvidenceTemplateItem)
        .filter(EvidenceTemplateItem.fault_category_id == request.fault_category_id)
        .all()
    )

    items: List[EvidenceItem] = (
        db.query(EvidenceItem)
        .filter(EvidenceItem.request_id == request.id)
        .all()
    )

    items_by_key = {item.template_key: item for item in items}
    
    total_templates = len(templates)
    mandatory_templates = [t for t in templates if t.mandatory]
    
    submitted_count = 0
    mandatory_submitted_count = 0
    missing_mandatory = []
    checklist_status = []

    for tmpl in templates:
        ev = items_by_key.get(tmpl.key)
        has_submission = ev is not None and ev.status != "REJECTED"
        if has_submission:
            submitted_count += 1
            if tmpl.mandatory:
                mandatory_submitted_count += 1
        elif tmpl.mandatory:
            missing_mandatory.append(tmpl.label)

        checklist_status.append({
            "template_id": tmpl.id,
            "key": tmpl.key,
            "label": tmpl.label,
            "type": tmpl.type,
            "mandatory": tmpl.mandatory,
            "who_submits": tmpl.who_submits,
            "is_submitted": has_submission,
            "evidence": {
                "id": ev.id,
                "file_url": ev.file_url,
                "text_value": ev.text_value,
                "status": ev.status,
                "presence_status": ev.presence_status,
                "reviewer_note": ev.reviewer_note,
                "captured_at": ev.captured_at.isoformat() if ev.captured_at else None
            } if ev else None
        })

    completeness_score = round(
        (mandatory_submitted_count / len(mandatory_templates) * 100.0) if mandatory_templates else 100.0,
        1
    )
    is_fully_complete = len(missing_mandatory) == 0

    return {
        "score_percentage": completeness_score,
        "is_complete": is_fully_complete,
        "submitted_count": submitted_count,
        "total_templates": total_templates,
        "mandatory_total": len(mandatory_templates),
        "mandatory_submitted": mandatory_submitted_count,
        "missing_mandatory": missing_mandatory,
        "summary": f"{mandatory_submitted_count}/{len(mandatory_templates)} mandatory items submitted" + (
            f": missing {', '.join(missing_mandatory)}" if missing_mandatory else " (All complete)"
        ),
        "items": checklist_status
    }
