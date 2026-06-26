"""Drop sniper: fire the instant a venue releases its tables.

Strategy:
  1. Sleep until just before the configured drop time.
  2. Pre-warm the connection so TLS/DNS is already done.
  3. Poll /find aggressively for a short burst around the drop instant
     (slots often appear a fraction of a second late), and book the first
     match. Stop as soon as we book or the burst window elapses.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from .booking import Attempt, try_book
from .client import ResyClient
from .config import Target
from .notify import announce

log = logging.getLogger("resy_bot.sniper")

# How early to wake before the drop, and how long/often to hammer afterward.
PREWARM_SECONDS = 5.0
BURST_DURATION = 20.0
BURST_INTERVAL = 0.25


async def _warm_connection(client: ResyClient, target: Target, day) -> None:
    try:
        await client.find_slots(target.venue_id, day, target.party_size)
    except Exception as e:
        log.debug("Pre-warm find failed (ok): %s", e)


async def snipe_one(client: ResyClient, target: Target, *, dry_run: bool) -> Attempt:
    """Wait for this target's drop, then burst-poll and book."""
    drop_at = target.next_drop_datetime()
    day = target.resolved_date(drop_at)
    log.info(
        "Sniping %s: drop at %s, booking date %s, party %d",
        target.name, drop_at.isoformat(), day, target.party_size,
    )

    now = datetime.now(target.tz)
    sleep_for = (drop_at - now).total_seconds() - PREWARM_SECONDS
    if sleep_for > 0:
        await asyncio.sleep(sleep_for)

    await _warm_connection(client, target, day)

    # Spin (cheaply) until the exact drop instant.
    while datetime.now(target.tz) < drop_at:
        await asyncio.sleep(0.02)

    log.info("DROP for %s — bursting.", target.name)
    deadline = asyncio.get_event_loop().time() + BURST_DURATION
    last: Attempt | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            attempt = await try_book(client, target, day, dry_run=dry_run)
        except Exception as e:
            log.warning("Snipe poll error for %s: %s", target.name, e)
            await asyncio.sleep(BURST_INTERVAL)
            continue

        last = attempt
        if attempt.booked or attempt.reason == "dry_run":
            await announce(attempt)
            return attempt
        await asyncio.sleep(BURST_INTERVAL)

    log.info("Snipe window for %s elapsed without a booking.", target.name)
    return last or Attempt(target, booked=False, reason="window elapsed")


async def run_sniper(client: ResyClient, targets: list[Target], *, dry_run: bool):
    """Snipe every configured target concurrently."""
    if not targets:
        return []
    results = await asyncio.gather(
        *(snipe_one(client, t, dry_run=dry_run) for t in targets),
        return_exceptions=True,
    )
    return results
