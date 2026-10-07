"""LLM Plugin Adapter supporting Google Gemini, Groq, and Rule-Based Fallbacks."""
import os
import json
import logging
from typing import Dict, Any, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger("sentinelops.llm")


async def generate_chat_response(prompt: str, system_prompt: str) -> Optional[str]:
    """Call Gemini API if key is available, else return None to trigger rule-based fallback."""
    if not settings.GEMINI_API_KEY:
        return None

    try:
        # Use Google GenAI REST endpoint directly for maximum portability
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\nUser Question:\n{prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 600
            }
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return text
    except Exception as e:
        logger.warning(f"Gemini API call failed or timed out: {e}")

    return None
