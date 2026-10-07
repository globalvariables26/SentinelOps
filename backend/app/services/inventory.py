"""Inventory, Service Kit, and Spare-Part Impact Chain Service."""
import json
from datetime import timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.models import (
    InventoryItem, StockLevel, KitItem, Reservation, PurchaseRequest,
    Site, Machine, FaultCategory, ServiceRequest
)
from app.plugins.distance import haversine_km, calculate_travel_minutes
from app.core.time import utcnow


def check_kit_availability(
    db: Session,
    site_id: int,
    fault_category_id: int
) -> Dict[str, Any]:
    """Check availability of all items in the fault category service kit across locations.
    Returns detailed availability report, shortage status, and recommendations.
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    kit_items = db.query(KitItem).filter(KitItem.fault_category_id == fault_category_id).all()
    
    kit_status = []
    has_shortage = False
    shortage_items = []

    for ki in kit_items:
        item = ki.item
        required_qty = ki.qty

        # 1. Check local site stock
        site_stock = (
            db.query(StockLevel)
            .filter(
                StockLevel.item_id == item.id,
                StockLevel.location_type == "SITE",
                StockLevel.location_id == site_id
            )
            .first()
        )
        local_available = (site_stock.on_hand - site_stock.reserved) if site_stock else 0

        # 2. Check technician van stock
        van_stocks = (
            db.query(StockLevel)
            .filter(
                StockLevel.item_id == item.id,
                StockLevel.location_type == "VAN"
            )
            .all()
        )
        van_available = sum(max(0, s.on_hand - s.reserved) for s in van_stocks)

        # 3. Check other sites
        other_site_stocks = (
            db.query(StockLevel)
            .filter(
                StockLevel.item_id == item.id,
                StockLevel.location_type == "SITE",
                StockLevel.location_id != site_id
            )
            .all()
        )

        transfer_options = []
        if site:
            for ost in other_site_stocks:
                available_qty = ost.on_hand - ost.reserved
                if available_qty > 0:
                    other_site = db.query(Site).filter(Site.id == ost.location_id).first()
                    if other_site:
                        dist = haversine_km(site.lat, site.lng, other_site.lat, other_site.lng)
                        eta_mins = calculate_travel_minutes(dist, prep_minutes=15.0)
                        transfer_options.append({
                            "site_id": other_site.id,
                            "site_name": other_site.name,
                            "distance_km": dist,
                            "eta_minutes": eta_mins,
                            "available_qty": available_qty
                        })

        # Sort transfer options by shortest ETA
        transfer_options.sort(key=lambda x: x["eta_minutes"])

        # 4. Check compatible substitutes
        substitutes = []
        if item.compat_group:
            sub_items = (
                db.query(InventoryItem)
                .filter(
                    InventoryItem.compat_group == item.compat_group,
                    InventoryItem.id != item.id
                )
                .all()
            )
            for sub in sub_items:
                sub_site_stock = (
                    db.query(StockLevel)
                    .filter(
                        StockLevel.item_id == sub.id,
                        StockLevel.location_type == "SITE",
                        StockLevel.location_id == site_id
                    )
                    .first()
                )
                sub_available = (sub_site_stock.on_hand - sub_site_stock.reserved) if sub_site_stock else 0
                if sub_available >= required_qty:
                    substitutes.append({
                        "item_id": sub.id,
                        "sku": sub.sku,
                        "name": sub.name,
                        "available_qty": sub_available
                    })

        is_item_available = local_available >= required_qty
        if not is_item_available:
            has_shortage = True
            shortage_items.append({
                "item_id": item.id,
                "sku": item.sku,
                "name": item.name,
                "required_qty": required_qty,
                "local_available": local_available,
                "transfer_options": transfer_options,
                "substitutes": substitutes
            })

        kit_status.append({
            "item_id": item.id,
            "sku": item.sku,
            "name": item.name,
            "kind": ki.kind,
            "required_qty": required_qty,
            "local_available": local_available,
            "van_available": van_available,
            "is_available": is_item_available,
            "transfer_available": len(transfer_options) > 0,
            "transfer_options": transfer_options,
            "substitutes": substitutes
        })

    return {
        "all_available": not has_shortage,
        "kit_items": kit_status,
        "shortage_items": shortage_items
    }


def compute_impact_chain(
    db: Session,
    machine: Machine,
    site: Site,
    priority: str,
    shortage_items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build the spare-part impact chain:
    Part Shortage -> Job Delay -> Machine Downtime -> SLA Risk -> Customer Impact
    """
    if not shortage_items:
        return {"has_impact": False, "summary": "All required service kit items available on site."}

    # Best transfer ETA or purchase lead time
    min_transfer_delay_h = 999.0
    best_transfer = None
    substitute_ready = False

    for item in shortage_items:
        if item.get("substitutes"):
            substitute_ready = True
        transfers = item.get("transfer_options", [])
        if transfers:
            first_transfer = transfers[0]
            delay_h = round(first_transfer["eta_minutes"] / 60.0, 1)
            if delay_h < min_transfer_delay_h:
                min_transfer_delay_h = delay_h
                best_transfer = first_transfer

    job_delay_h = 0.0
    recovery_strategy = "Local Stock"
    if substitute_ready:
        job_delay_h = 0.5  # 30 min retooling
        recovery_strategy = "Use Compatible Substitute"
    elif best_transfer:
        job_delay_h = min_transfer_delay_h
        recovery_strategy = f"Inter-Site Transfer from Site B ({best_transfer['site_name']}, {best_transfer['distance_km']} km, ~{int(best_transfer['eta_minutes'])} min)"
    else:
        job_delay_h = 24.0  # Expedited purchase order
        recovery_strategy = "Emergency Procurement (24h lead time)"

    machine_downtime_h = job_delay_h + 2.5  # Delay + estimated repair time

    sla_risk_level = "SAFE"
    if priority == "CRITICAL" and job_delay_h > 2.0:
        sla_risk_level = "CRITICAL"
    elif priority in ("CRITICAL", "HIGH") and job_delay_h > 1.0:
        sla_risk_level = "AT_RISK"

    chain = {
        "has_impact": True,
        "part_shortage": f"{len(shortage_items)} item(s) out of stock at {site.name} ({', '.join(s['name'] for s in shortage_items)})",
        "job_delay_hours": job_delay_h,
        "machine_downtime_hours": machine_downtime_h,
        "sla_risk": sla_risk_level,
        "customer_impact": f"{machine.site.customer.name} - {machine.code} ({machine.criticality} criticality press down at {site.name})",
        "recommended_recovery": recovery_strategy,
        "best_transfer": best_transfer,
        "substitute_available": substitute_ready
    }
    return chain


def reserve_service_kit(
    db: Session,
    request: ServiceRequest,
    plan_part_source: str = "SITE"
) -> List[Reservation]:
    """Atomically reserve all items needed for the request's fault category.
    Handles site stock, transfers, or van stock based on chosen plan.
    """
    kit_items = db.query(KitItem).filter(KitItem.fault_category_id == request.fault_category_id).all()
    reservations = []

    for ki in kit_items:
        item = ki.item
        qty = ki.qty

        # Local site stock check
        site_stock = (
            db.query(StockLevel)
            .filter(
                StockLevel.item_id == item.id,
                StockLevel.location_type == "SITE",
                StockLevel.location_id == request.site_id
            )
            .first()
        )

        if site_stock and (site_stock.on_hand - site_stock.reserved) >= qty:
            site_stock.reserved += qty
            res = Reservation(
                request_id=request.id,
                item_id=item.id,
                qty=qty,
                source_location=request.site.name,
                source_type="SITE",
                source_location_id=request.site_id,
                status="RESERVED",
                created_at=utcnow()
            )
            db.add(res)
            reservations.append(res)
        else:
            # Need transfer from another site
            other_site_stock = (
                db.query(StockLevel)
                .filter(
                    StockLevel.item_id == item.id,
                    StockLevel.location_type == "SITE",
                    StockLevel.location_id != request.site_id,
                    (StockLevel.on_hand - StockLevel.reserved) >= qty
                )
                .first()
            )
            if other_site_stock:
                other_site = db.query(Site).filter(Site.id == other_site_stock.location_id).first()
                dist = haversine_km(request.site.lat, request.site.lng, other_site.lat, other_site.lng)
                eta_mins = calculate_travel_minutes(dist)
                other_site_stock.reserved += qty
                res = Reservation(
                    request_id=request.id,
                    item_id=item.id,
                    qty=qty,
                    source_location=f"{other_site.name} (Transfer)",
                    source_type="TRANSFER",
                    source_location_id=other_site.id,
                    status="IN_TRANSIT",
                    eta=utcnow() + timedelta(minutes=eta_mins),
                    created_at=utcnow()
                )
                db.add(res)
                reservations.append(res)
            else:
                # Check van stock or warehouse
                res = Reservation(
                    request_id=request.id,
                    item_id=item.id,
                    qty=qty,
                    source_location="Central Warehouse / Sourcing",
                    source_type="WAREHOUSE",
                    source_location_id=0,
                    status="RESERVED",
                    created_at=utcnow()
                )
                db.add(res)
                reservations.append(res)

    db.commit()
    return reservations


def release_reservations(db: Session, request_id: int):
    """Release all reserved stock held for a request (e.g. on dropout or cancellation)."""
    reservations = db.query(Reservation).filter(
        Reservation.request_id == request_id,
        Reservation.status.in_(["RESERVED", "IN_TRANSIT"])
    ).all()

    for res in reservations:
        if res.source_location_id:
            stock = (
                db.query(StockLevel)
                .filter(
                    StockLevel.item_id == res.item_id,
                    StockLevel.location_id == res.source_location_id
                )
                .first()
            )
            if stock:
                stock.reserved = max(0, stock.reserved - res.qty)
        res.status = "RELEASED"

    db.commit()


def issue_reserved_kit(db: Session, request_id: int):
    """Deduct inventory stock when service request is verified."""
    reservations = db.query(Reservation).filter(
        Reservation.request_id == request_id,
        Reservation.status.in_(["RESERVED", "IN_TRANSIT"])
    ).all()

    for res in reservations:
        if res.source_location_id:
            stock = (
                db.query(StockLevel)
                .filter(
                    StockLevel.item_id == res.item_id,
                    StockLevel.location_id == res.source_location_id
                )
                .first()
            )
            if stock:
                stock.on_hand = max(0, stock.on_hand - res.qty)
                stock.reserved = max(0, stock.reserved - res.qty)
        res.status = "ISSUED"

    db.commit()
