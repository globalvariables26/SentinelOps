"""Machine and Digital Passport API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Machine, User, Site
from app.core.deps import get_current_user, require_role
from app.services.passport import get_machine_passport, create_preventive_plan
from app.plugins.qr import generate_machine_qr_bytes

router = APIRouter(prefix="/machines", tags=["Machines"])


@router.get("")
def list_machines(
    site_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List machines with optional site filter. Enforces customer tenancy scoping."""
    query = db.query(Machine).join(Site)
    if current_user.role == "CUSTOMER" and current_user.customer_id:
        query = query.filter(Site.customer_id == current_user.customer_id)
    if site_id:
        query = query.filter(Machine.site_id == site_id)

    machines = query.all()
    return [
        {
            "id": m.id,
            "code": m.code,
            "model": m.model,
            "serial": m.serial,
            "site_id": m.site_id,
            "site_name": m.site.name,
            "criticality": m.criticality,
            "status": m.status,
            "health_score": m.health_score,
            "contract_active": m.contract_active,
            "qr_token": m.qr_token
        }
        for m in machines
    ]


@router.get("/qr-sheet")
def get_qr_sheet(db: Session = Depends(get_db)):
    """Return list of all machines with QR code URLs for printable physical sheet."""
    machines = db.query(Machine).all()
    return [
        {
            "id": m.id,
            "code": m.code,
            "model": m.model,
            "site_name": m.site.name,
            "qr_url": f"/api/machines/{m.id}/qr.png",
            "passport_url": f"/m/{m.qr_token}"
        }
        for m in machines
    ]


@router.get("/qr/{token}")
def get_machine_by_qr(token: str, db: Session = Depends(get_db)):
    """Public QR lookup used when a physical machine tag is scanned."""
    machine = db.query(Machine).filter(Machine.qr_token == token).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine QR not found")
    return get_machine_passport(db, machine.id)


@router.get("/{id}")
def get_machine(id: int, db: Session = Depends(get_db)):
    """Get single machine details."""
    machine = db.query(Machine).filter(Machine.id == id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    return {
        "id": machine.id,
        "code": machine.code,
        "model": machine.model,
        "serial": machine.serial,
        "site_id": machine.site_id,
        "site_name": machine.site.name,
        "criticality": machine.criticality,
        "status": machine.status,
        "health_score": machine.health_score,
        "contract_active": machine.contract_active,
        "qr_token": machine.qr_token
    }


@router.get("/{id}/passport")
def get_passport_endpoint(id: int, db: Session = Depends(get_db)):
    """Get Digital Machine Passport with health score, MTBF, MTTR, and timeline."""
    try:
        return get_machine_passport(db, id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{id}/qr.png")
def get_machine_qr(id: int, db: Session = Depends(get_db)):
    """Return PNG QR code image for machine physical tagging."""
    machine = db.query(Machine).filter(Machine.id == id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    qr_bytes = generate_machine_qr_bytes(machine.qr_token)
    return Response(content=qr_bytes, media_type="image/png")


@router.post("/{id}/preventive-plan")
def trigger_preventive_plan(
    id: int,
    fault_category_id: int,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Execute Failure Prevention Loop: Create a PREVENTIVE service request and bump min stock."""
    new_req = create_preventive_plan(db, id, fault_category_id, current_user.id)
    return {
        "message": "Preventive inspection plan successfully created and stock safety minimum elevated.",
        "request_id": new_req.id,
        "request_code": new_req.code
    }
