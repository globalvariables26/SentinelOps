"""Inventory, Stock Management, Transfers, and Procurement endpoints."""
from typing import List, Optional
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import InventoryItem, StockLevel, Reservation, PurchaseRequest, Site, User
from app.core.deps import require_role
from app.schemas.schemas import TransferCreate, PurchaseRequestCreate
from app.plugins.distance import haversine_km, calculate_travel_minutes
from app.core.time import utcnow

router = APIRouter(prefix="/inventory", tags=["Inventory & Spare Parts"])


@router.get("")
def get_inventory_status(db: Session = Depends(get_db)):
    """Fetch complete inventory posture: items, stock by location, active reservations, and purchase requests."""
    items = db.query(InventoryItem).all()
    stock_overview = []
    low_stock_alerts = []

    for item in items:
        stocks = db.query(StockLevel).filter(StockLevel.item_id == item.id).all()
        stock_by_loc = []
        total_on_hand = 0
        total_reserved = 0

        for s in stocks:
            loc_label = f"Site #{s.location_id}"
            if s.location_type == "SITE":
                site = db.query(Site).filter(Site.id == s.location_id).first()
                loc_label = site.name if site else f"Site {s.location_id}"
            elif s.location_type == "WAREHOUSE":
                loc_label = "Central Warehouse"
            elif s.location_type == "VAN":
                loc_label = f"Technician Van #{s.location_id}"

            stock_by_loc.append({
                "location_type": s.location_type,
                "location_id": s.location_id,
                "location_name": loc_label,
                "on_hand": s.on_hand,
                "reserved": s.reserved,
                "available": max(0, s.on_hand - s.reserved),
                "min_level": s.min_level
            })
            total_on_hand += s.on_hand
            total_reserved += s.reserved

            if (s.on_hand - s.reserved) < s.min_level:
                low_stock_alerts.append({
                    "item_id": item.id,
                    "sku": item.sku,
                    "name": item.name,
                    "location": loc_label,
                    "on_hand": s.on_hand,
                    "min_level": s.min_level
                })

        stock_overview.append({
            "id": item.id,
            "sku": item.sku,
            "name": item.name,
            "kind": item.kind,
            "unit_cost": item.unit_cost,
            "compat_group": item.compat_group,
            "total_on_hand": total_on_hand,
            "total_reserved": total_reserved,
            "total_available": max(0, total_on_hand - total_reserved),
            "locations": stock_by_loc
        })

    # Active reservations
    reservations = (
        db.query(Reservation)
        .filter(Reservation.status.in_(["RESERVED", "IN_TRANSIT"]))
        .order_by(Reservation.created_at.desc())
        .all()
    )
    res_list = [
        {
            "id": r.id,
            "request_id": r.request_id,
            "item_name": r.item.name,
            "sku": r.item.sku,
            "qty": r.qty,
            "source": r.source_location,
            "status": r.status,
            "eta": r.eta.isoformat() if r.eta else None
        }
        for r in reservations
    ]

    # Purchase requests
    prs = db.query(PurchaseRequest).order_by(PurchaseRequest.created_at.desc()).all()
    pr_list = [
        {
            "id": pr.id,
            "item_name": pr.item.name,
            "sku": pr.item.sku,
            "qty": pr.qty,
            "reason": pr.reason,
            "status": pr.status,
            "lead_time_h": pr.lead_time_h,
            "created_at": pr.created_at.isoformat()
        }
        for pr in prs
    ]

    return {
        "items": stock_overview,
        "low_stock_alerts": low_stock_alerts,
        "active_reservations": res_list,
        "purchase_requests": pr_list
    }


@router.post("/transfer")
def initiate_stock_transfer(
    data: TransferCreate,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Initiate an inter-site transfer with travel ETA calculation."""
    from_site = db.query(Site).filter(Site.id == data.from_site_id).first()
    to_site = db.query(Site).filter(Site.id == data.to_site_id).first()
    if not from_site or not to_site:
        raise HTTPException(status_code=404, detail="Source or target site not found")

    dist = haversine_km(from_site.lat, from_site.lng, to_site.lat, to_site.lng)
    eta_mins = calculate_travel_minutes(dist, prep_minutes=15.0)

    # Check source stock
    stock = (
        db.query(StockLevel)
        .filter(
            StockLevel.item_id == data.item_id,
            StockLevel.location_type == "SITE",
            StockLevel.location_id == data.from_site_id
        )
        .first()
    )
    if not stock or (stock.on_hand - stock.reserved) < data.qty:
        raise HTTPException(status_code=400, detail="Insufficient stock available at source site.")

    # Deduct from source and add to destination
    stock.on_hand -= data.qty

    dest_stock = (
        db.query(StockLevel)
        .filter(
            StockLevel.item_id == data.item_id,
            StockLevel.location_type == "SITE",
            StockLevel.location_id == data.to_site_id
        )
        .first()
    )
    if not dest_stock:
        dest_stock = StockLevel(
            item_id=data.item_id,
            location_type="SITE",
            location_id=data.to_site_id,
            on_hand=data.qty,
            reserved=0,
            min_level=2
        )
        db.add(dest_stock)
    else:
        dest_stock.on_hand += data.qty

    db.commit()

    return {
        "message": f"Transferred {data.qty} units from {from_site.name} to {to_site.name}.",
        "distance_km": dist,
        "eta_minutes": eta_mins
    }


@router.post("/purchase-request")
def create_purchase_request(
    data: PurchaseRequestCreate,
    current_user: User = Depends(require_role(["ADMIN", "MANAGER"])),
    db: Session = Depends(get_db)
):
    """Create a draft purchase request for parts shortage."""
    pr = PurchaseRequest(
        item_id=data.item_id,
        qty=data.qty,
        reason=data.reason,
        status="SUBMITTED",
        lead_time_h=data.lead_time_h,
        created_at=utcnow()
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)

    return {
        "id": pr.id,
        "message": "Purchase request submitted.",
        "item_name": pr.item.name,
        "lead_time_h": pr.lead_time_h
    }
