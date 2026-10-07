"""User Management API endpoints for Administrators."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.core.deps import require_role
from app.core.security import get_password_hash
from app.schemas.schemas import UserCreate

router = APIRouter(prefix="/users", tags=["Users Management"])


@router.get("")
def list_users(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """List all system users."""
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "customer_id": u.customer_id,
            "created_at": u.created_at.isoformat()
        }
        for u in users
    ]


@router.post("")
def create_user(
    data: UserCreate,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Create a new user."""
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists.")

    new_user = User(
        email=data.email,
        name=data.name,
        role=data.role,
        customer_id=data.customer_id,
        hashed_password=get_password_hash(data.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "id": new_user.id,
        "email": new_user.email,
        "name": new_user.name,
        "role": new_user.role
    }


@router.delete("/{id}")
def delete_user(
    id: int,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Delete a user."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": f"User {user.email} deleted."}
