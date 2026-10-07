"""Notification plugins: in-app persistence, WebSocket broadcast, and Telegram bot."""
import logging
import httpx
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.models import Notification, User

logger = logging.getLogger("sentinelops.notifier")


def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send alert via Telegram Bot API."""
    if not settings.TELEGRAM_BOT_TOKEN or not chat_id:
        logger.info(f"[SIMULATED] Telegram not sent (token or chat_id missing): {text[:60]}")
        return False
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = httpx.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=5.0)
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Failed to deliver telegram alert: {e}")
        return False


def create_in_app_notification(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    level: str = "INFO",
    link: Optional[str] = None
) -> Notification:
    """Persist notification to database and trigger outbound notifications."""
    notif = Notification(
        user_id=user_id,
        title=title,
        body=body,
        level=level,
        link=link
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # If user has a telegram chat id, attempt send
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.telegram_chat_id:
        tg_text = f"🚨 <b>SentinelOps Alert: {title}</b>\n\n{body}"
        if link:
            tg_text += f"\n\nLink: {link}"
        send_telegram_message(user.telegram_chat_id, tg_text)

    return notif
