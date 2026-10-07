"""Storage Provider Interface and Local File / Supabase implementations."""
import os
import uuid
import shutil
from typing import Optional
from fastapi import UploadFile
from app.core.config import settings

LOCAL_STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)


async def save_upload_file(file: UploadFile, prefix: str = "evidence") -> str:
    """Save an uploaded file and return public access URL or path."""
    ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    unique_filename = f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"

    if settings.STORAGE_BACKEND == "supabase" and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        # Supabase upload logic
        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
                "Content-Type": file.content_type or "image/jpeg"
            }
            content = await file.read()
            url = f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_BUCKET}/{unique_filename}"
            async with httpx.AsyncClient() as client:
                res = await client.post(url, headers=headers, content=content)
                if res.status_code in (200, 201):
                    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_BUCKET}/{unique_filename}"
        except Exception:
            pass

    # Default to Local file storage
    local_path = os.path.join(LOCAL_STORAGE_DIR, unique_filename)
    with open(local_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    return f"/uploads/{unique_filename}"
