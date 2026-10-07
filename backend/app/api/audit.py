"""Audit Log and Cryptographic Integrity Verification API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import AuditLog, User
from app.core.deps import require_role
from app.core.config import settings
from app.services.audit import verify_chain, tamper_audit_log

router = APIRouter(prefix="/audit", tags=["Audit & Provenance"])


@router.get("")
def list_audit_entries(
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """List cryptographic audit log entries with SHA-256 hashes and previous block linkages."""
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)

    entries = query.order_by(AuditLog.seq.desc()).limit(limit).all()
    import json
    return [
        {
            "id": e.id,
            "seq": e.seq,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "action": e.action,
            "actor_id": e.actor_id,
            "actor_role": e.actor_role,
            "before": json.loads(e.before_state) if e.before_state else None,
            "after": json.loads(e.after_state) if e.after_state else None,
            "meta": json.loads(e.meta) if e.meta else None,
            "ts": e.ts.isoformat(),
            "prev_hash": e.prev_hash,
            "hash": e.hash
        }
        for e in entries
    ]


@router.get("/verify")
def verify_audit_integrity(db: Session = Depends(get_db)):
    """Walk the complete SHA-256 hash chain and report tamper status."""
    is_valid, broken_seq, message, total_verified = verify_chain(db)
    return {
        "is_valid": is_valid,
        "broken_seq": broken_seq,
        "message": message,
        "total_verified": total_verified
    }


@router.post("/tamper")
def simulate_tampering(
    seq: int = Query(...),
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Simulate malicious tampering on a record to demonstrate cryptographic detection (DEMO_MODE only)."""
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Tampering simulation disabled in production mode.")

    success = tamper_audit_log(db, seq, new_action="[MALICIOUS TAMPERING SIMULATED]")
    if not success:
        raise HTTPException(status_code=404, detail="Audit entry seq not found")

    return {
        "message": f"Simulated tampering applied to audit entry #{seq}. Run 'Verify Integrity' to observe detection.",
        "tampered_seq": seq
    }
