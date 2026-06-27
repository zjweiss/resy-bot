"""Shared find -> choose -> book flow used by both the sniper and watcher."""

from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date as date_cls

from .client import BookingError, ResyClient
from .config import Target
from .matching import choose_slot

log = logging.getLogger("resy_bot.booking")


@dataclass
class Attempt:
    """The outcome of one find -> choose -> book attempt for a target."""

    target: Target
    booked: bool
    slot_time: str | None = None
    table_type: str | None = None
    reason: str | None = None       # why nothing was booked
    confirmation: dict | None = None


async def try_book(  # pylint: disable=too-many-arguments,too-many-return-statements
    client: ResyClient,
    target: Target,
    day: date_cls,
    *,
    dry_run: bool,
    commit_lock: asyncio.Lock | None = None,
    stop_event: asyncio.Event | None = None,
) -> Attempt:
    """Run one full booking attempt for a target on a specific day.

    `commit_lock` + `stop_event` coordinate a group of targets so at most one
    booking is committed: the first to commit sets `stop_event`, and any other
    target aborts before reserving. Pass neither for a standalone attempt.
    """
    if stop_event is not None and stop_event.is_set():
        return Attempt(target, booked=False, reason="superseded by another booking")

    slots = await client.find_slots(target.venue_id, day, target.party_size)
    if not slots:
        return Attempt(target, booked=False, reason="no slots returned")

    slot = choose_slot(slots, target)
    if slot is None:
        return Attempt(
            target,
            booked=False,
            reason=f"{len(slots)} slot(s) found, none matched preferences",
        )

    if dry_run:
        log.info(
            "[dry-run] would book %s @ %s (%s) on %s",
            target.name, slot.clock, slot.table_type or "any", day,
        )
        return Attempt(
            target, booked=False, slot_time=slot.clock,
            table_type=slot.table_type, reason="dry_run",
        )

    # Serialize the actual commit across the group and re-check the gate once
    # we hold the lock, so a sibling that booked a beat earlier wins cleanly.
    async with (commit_lock if commit_lock is not None else nullcontext()):
        if stop_event is not None and stop_event.is_set():
            return Attempt(
                target, booked=False, slot_time=slot.clock,
                table_type=slot.table_type, reason="superseded by another booking",
            )
        try:
            book_token = await client.get_book_token(
                slot.config_token, day, target.party_size
            )
            confirmation = await client.book(book_token)
        except BookingError as e:
            # Common when another user grabbed the same slot a beat earlier.
            log.warning("Booking %s @ %s failed: %s", target.name, slot.clock, e)
            return Attempt(
                target, booked=False, slot_time=slot.clock,
                table_type=slot.table_type, reason=str(e),
            )
        if stop_event is not None:
            stop_event.set()

    return Attempt(
        target, booked=True, slot_time=slot.clock,
        table_type=slot.table_type, confirmation=confirmation,
    )
