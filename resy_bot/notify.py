"""Notifications. Logs everywhere; optionally posts to a webhook (Slack/Discord)."""

from __future__ import annotations

import logging
import os

import httpx

from .booking import Attempt

log = logging.getLogger("resy_bot.notify")

# Set RESY_BOT_WEBHOOK to a Slack/Discord incoming-webhook URL to get pings.
WEBHOOK_URL = os.environ.get("RESY_BOT_WEBHOOK")


async def announce(attempt: Attempt) -> None:
    if attempt.booked:
        msg = (
            f"✅ BOOKED {attempt.target.name} @ {attempt.slot_time} "
            f"({attempt.table_type or 'table'}) for {attempt.target.party_size}"
        )
        log.info(msg)
    else:
        log.debug("No booking for %s: %s", attempt.target.name, attempt.reason)
        msg = None

    if msg and WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                await c.post(WEBHOOK_URL, json={"text": msg, "content": msg})
        except Exception as e:  # never let a notification failure break booking
            log.warning("Webhook post failed: %s", e)
