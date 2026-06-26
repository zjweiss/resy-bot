"""Watchlist poller: grab cancellations as they appear on a fixed date.

Each target is polled on its own interval. The first matching slot that we can
book wins; once booked, that target drops out of the rotation.
"""

from __future__ import annotations

import asyncio
import logging

from .booking import try_book
from .client import ResyClient
from .config import Target
from .notify import announce

log = logging.getLogger("resy_bot.watcher")


async def watch_one(client: ResyClient, target: Target, *, dry_run: bool) -> None:
    day = target.resolved_date()
    log.info(
        "Watching %s on %s (party %d, every %.0fs)",
        target.name, day, target.party_size, target.poll_interval,
    )
    while True:
        try:
            attempt = await try_book(client, target, day, dry_run=dry_run)
            if attempt.booked:
                await announce(attempt)
                return
            if attempt.reason == "dry_run":
                # In dry-run we found a match; announce once and keep watching
                # so you can see availability without exiting.
                await announce(attempt)
            else:
                log.debug("%s: %s", target.name, attempt.reason)
        except Exception as e:
            log.warning("Watch poll error for %s: %s", target.name, e)

        await asyncio.sleep(target.poll_interval)


async def run_watcher(client: ResyClient, targets: list[Target], *, dry_run: bool):
    if not targets:
        return
    await asyncio.gather(
        *(watch_one(client, t, dry_run=dry_run) for t in targets),
        return_exceptions=True,
    )
