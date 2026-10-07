"""In-process Domain Event Bus with persistent event ledger."""
import json
import logging
from typing import Callable, Dict, List, Any
from sqlalchemy.orm import Session
from app.db.models import DomainEvent
from app.core.time import utcnow

logger = logging.getLogger("sentinelops.events")
_subscribers: Dict[str, List[Callable[[str, Dict[str, Any], Session], None]]] = {}


def subscribe(event_type: str, handler: Callable[[str, Dict[str, Any], Session], None]):
    """Subscribe a handler to an event pattern or specific type."""
    if event_type not in _subscribers:
        _subscribers[event_type] = []
    _subscribers[event_type].append(handler)


def emit(event_type: str, payload: Dict[str, Any], actor: str, db: Session):
    """Persist event to DomainEvent ledger and invoke synchronous handlers."""
    try:
        event = DomainEvent(
            type=event_type,
            payload=json.dumps(payload, default=str),
            actor=actor,
            created_at=utcnow()
        )
        db.add(event)
        db.commit()
    except Exception as e:
        logger.error(f"Error persisting DomainEvent {event_type}: {e}")

    # Invoke exact subscribers and wildcard '*' subscribers
    handlers = _subscribers.get(event_type, []) + _subscribers.get("*", [])
    for h in handlers:
        try:
            h(event_type, payload, db)
        except Exception as e:
            logger.error(f"Error in handler {h.__name__} for event {event_type}: {e}")
