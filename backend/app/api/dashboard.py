"""Dashboard Control Tower and Metrics endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.deps import get_current_user
from app.db.models import User
from app.services.metrics import get_control_tower_data, get_system_metrics

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/tower")
def get_tower(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fetch live Control Tower overview: KPI strip, heat strip, attention cards, and charts."""
    return get_control_tower_data(db, current_user)


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    """Fetch honest system baseline metrics and impact descriptions."""
    return get_system_metrics(db)
