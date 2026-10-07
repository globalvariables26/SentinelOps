"""Cryptographic Hash-Chained Audit Log Service.
Guarantees tamper-evident audit trail with SHA-256 hash chaining.
"""
import hashlib
import json
import threading
from typing import Optional, Dict, Any, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models import AuditLog
from app.core.time import utcnow

# Single-worker in-process lock for sequential hash chaining
_audit_lock = threading.Lock()
GENESIS_HASH = "0" * 64


def canonical_json(obj: Any) -> str:
    """Produce deterministic canonical JSON string with sorted keys."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)


def compute_entry_hash(prev_hash: str, payload_dict: Dict[str, Any]) -> str:
    """Compute sha256(prev_hash + canonical_json(payload))."""
    serialized = canonical_json(payload_dict)
    combined = f"{prev_hash}{serialized}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def append_audit_log(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    actor_id: Optional[int],
    actor_role: str,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None
) -> AuditLog:
    """Atomically append a new entry to the cryptographic hash chain."""
    with _audit_lock:
        last_entry = db.query(AuditLog).order_by(AuditLog.seq.desc()).first()
        if last_entry is None:
            next_seq = 1
            prev_hash = GENESIS_HASH
        else:
            next_seq = last_entry.seq + 1
            prev_hash = last_entry.hash

        current_time = utcnow()
        
        # Prepare deterministic payload for hashing
        payload = {
            "seq": next_seq,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "before_state": before,
            "after_state": after,
            "meta": meta,
            "ts": current_time.isoformat()
        }

        entry_hash = compute_entry_hash(prev_hash, payload)

        log_entry = AuditLog(
            seq=next_seq,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            before_state=json.dumps(before) if before else None,
            after_state=json.dumps(after) if after else None,
            meta=json.dumps(meta) if meta else None,
            ts=current_time,
            prev_hash=prev_hash,
            hash=entry_hash
        )

        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry


def verify_chain(db: Session) -> Tuple[bool, Optional[int], str, int]:
    """Walk the audit chain from genesis to tip and verify cryptographic integrity.
    Returns: (is_valid, broken_seq_or_none, message, total_verified)
    """
    entries: List[AuditLog] = db.query(AuditLog).order_by(AuditLog.seq.asc()).all()
    if not entries:
        return True, None, "Audit chain is empty. Clean state.", 0

    expected_prev = GENESIS_HASH
    for i, entry in enumerate(entries):
        # 1. Verify sequence increment
        if entry.seq != (i + 1):
            return False, entry.seq, f"Sequence gap at record #{entry.seq} (expected {i + 1})", i

        # 2. Verify prev_hash link
        if entry.prev_hash != expected_prev:
            return (
                False,
                entry.seq,
                f"Broken link at sequence #{entry.seq}: prev_hash does not match preceding entry hash.",
                i
            )

        # 3. Recompute hash
        payload = {
            "seq": entry.seq,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "action": entry.action,
            "actor_id": entry.actor_id,
            "actor_role": entry.actor_role,
            "before_state": json.loads(entry.before_state) if entry.before_state else None,
            "after_state": json.loads(entry.after_state) if entry.after_state else None,
            "meta": json.loads(entry.meta) if entry.meta else None,
            "ts": entry.ts.isoformat()
        }
        recomputed = compute_entry_hash(entry.prev_hash, payload)
        if recomputed != entry.hash:
            return (
                False,
                entry.seq,
                f"Tampering detected at sequence #{entry.seq}: payload hash mismatch.",
                i
            )

        expected_prev = entry.hash

    return True, None, f"All {len(entries)} audit entries successfully verified against SHA-256 chain.", len(entries)


def tamper_audit_log(db: Session, seq: int, new_action: str = "[TAMPERED DATA]") -> bool:
    """Simulate malicious tampering with an audit entry (DEMO_MODE only)."""
    entry = db.query(AuditLog).filter(AuditLog.seq == seq).first()
    if not entry:
        return False
    entry.action = new_action
    db.commit()
    return True
