"""Grounded Ops Copilot API endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.core.deps import get_current_user
from app.services.copilot import answer_copilot_query
from app.schemas.schemas import CopilotQueryRequest

router = APIRouter(prefix="/copilot", tags=["Ops Copilot"])


@router.post("/chat")
async def copilot_chat(
    data: CopilotQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Chat with the Grounded Ops Copilot. Facts are strictly retrieved from real database state."""
    response_text = await answer_copilot_query(db, data.message, current_user)
    return {
        "reply": response_text,
        "user_role": current_user.role
    }
