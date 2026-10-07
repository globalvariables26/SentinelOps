"""Test suite for Cryptographic Hash-Chained Audit Log."""
import pytest
from app.db.session import SessionLocal
from app.services.audit import append_audit_log, verify_chain, tamper_audit_log


def test_audit_hash_chain():
    db = SessionLocal()
    try:
        # Verify initial chain integrity
        is_valid, broken_seq, msg, count = verify_chain(db)
        assert is_valid is True, f"Initial chain invalid: {msg}"
        initial_count = count

        # Append new event
        entry = append_audit_log(
            db=db,
            entity_type="TestEntity",
            entity_id=999,
            action="TEST_ACTION",
            actor_id=1,
            actor_role="ADMIN",
            before={"state": "A"},
            after={"state": "B"},
            meta={"test": True}
        )
        assert entry.seq == initial_count + 1
        assert len(entry.hash) == 64
        assert len(entry.prev_hash) == 64

        # Chain must still verify
        is_valid, broken_seq, msg, count = verify_chain(db)
        assert is_valid is True
        assert count == initial_count + 1

        # Test tamper detection
        tampered = tamper_audit_log(db, entry.seq, new_action="CORRUPTED_ACTION")
        assert tampered is True

        is_valid_after, broken_seq_after, msg_after, _ = verify_chain(db)
        assert is_valid_after is False
        assert broken_seq_after == entry.seq
        assert "Tampering detected" in msg_after

    finally:
        db.close()
