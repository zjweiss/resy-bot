"""Choosing the best slot from what Resy returns, given a Target's preferences."""

from __future__ import annotations

from datetime import time

from .client import Slot
from .config import Target


def _clock_to_time(clock: str) -> time | None:
    try:
        h, m = clock.split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, IndexError):
        return None


def _eligible(slot: Slot, target: Target) -> bool:
    """Does this slot satisfy the target's hard constraints?"""
    if target.table_types:
        if slot.table_type not in target.table_types:
            return False

    if target.time_window is not None:
        t = _clock_to_time(slot.clock)
        if t is None:
            return False
        lo, hi = target.time_window
        if not (lo <= t <= hi):
            return False

    return True


def _rank(slot: Slot, target: Target) -> tuple:
    """Sort key: lower is better.

    Prefer slots whose clock time appears earliest in `preferred_times`;
    slots not in the preferred list fall back to closeness to the first
    preferred time (or just chronological order if none specified).
    """
    t = _clock_to_time(slot.clock)
    prefs = target.preferred_times

    if t is not None and t in prefs:
        return (0, prefs.index(t))

    if t is not None and prefs:
        # Minutes away from the top preference.
        anchor = prefs[0]
        delta = abs(
            (t.hour * 60 + t.minute) - (anchor.hour * 60 + anchor.minute)
        )
        return (1, delta)

    return (2, slot.clock)


def choose_slot(slots: list[Slot], target: Target) -> Slot | None:
    """Return the single best slot to book, or None if nothing matches."""
    eligible = [s for s in slots if s.config_token and _eligible(s, target)]
    if not eligible:
        return None
    eligible.sort(key=lambda s: _rank(s, target))
    return eligible[0]
