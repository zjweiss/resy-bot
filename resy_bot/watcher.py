"""Watchlist poller: grab cancellations as they appear on a fixed date.

Each target is polled on its own interval. Targets are grouped by reservation
date: within a night, the first target to book wins and all other targets for
that same night stop immediately, so you never end up with two reservations on
the same evening. Different nights are independent.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from .booking import try_book
from .client import ResyClient
from .config import Target
from .notify import announce

log = logging.getLogger("resy_bot.watcher")


async def watch_one(
    client: ResyClient,
    target: Target,
    *,
    dry_run: bool,
    commit_lock: asyncio.Lock,
    stop_event: asyncio.Event,
) -> None:
    """Poll a single target until it books, a sibling books its night, or forever (dry-run)."""
    day = target.resolved_date()
    log.info(
        "Watching %s on %s (party %d, every %.0fs)",
        target.name, day, target.party_size, target.poll_interval,
    )
    while True:
        if stop_event.is_set():
            log.info(
                "%s: another table for %s already booked — stopping watch.",
                target.name, day,
            )
            return
        try:
            attempt = await try_book(
                client, target, day,
                dry_run=dry_run, commit_lock=commit_lock, stop_event=stop_event,
            )
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
    """Watch all targets, booking at most one reservation per night."""
    if not targets:
        return

    # Group by reservation date so each night shares one lock + stop flag.
    by_night: dict = defaultdict(list)
    for t in targets:
        by_night[t.resolved_date()].append(t)

    coros = []
    for night_targets in by_night.values():
        lock = asyncio.Lock()
        stop = asyncio.Event()
        for t in night_targets:
            coros.append(
                watch_one(client, t, dry_run=dry_run, commit_lock=lock, stop_event=stop)
            )

    await asyncio.gather(*coros, return_exceptions=True)
