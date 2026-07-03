import logging
from typing import Any

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)


async def send_calendar_action(payload: dict[str, Any]) -> bool:
    settings = get_settings()
    if not settings.n8n_webhook_url:
        logger.warning("N8N_WEBHOOK_URL missing; calendar action not sent")
        return False

    headers = {"Content-Type": "application/json"}
    if settings.n8n_webhook_token:
        headers["Authorization"] = f"Bearer {settings.n8n_webhook_token}"

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(settings.n8n_webhook_url, json=payload, headers=headers)
        response.raise_for_status()
    return True
