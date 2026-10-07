"""Notification service: routes notifications to appropriate roles and channels."""
from typing import List, Optional
from sqlalchemy.orm import Session
from app.db.models import User, Notification
from app.plugins.notifier import create_in_app_notification


def notify_users_by_role(
    db: Session,
    roles: List[str],
    title: str,
    body: str,
    level: str = "INFO",
    link: Optional[str] = None
):
    """Notify all users with specified roles."""
    users = db.query(User).filter(User.role.in_(roles)).all()
    for user in users:
        create_in_app_notification(db, user.id, title, body, level, link)


def notify_user(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    level: str = "INFO",
    link: Optional[str] = None
) -> Notification:
    """Notify a specific user."""
    return create_in_app_notification(db, user_id, title, body, level, link)
