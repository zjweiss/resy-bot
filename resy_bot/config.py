"""Configuration loading and typed models for the Resy bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


def _parse_time(value: str) -> time:
    """Parse an "HH:MM" (or "HH:MM:SS") clock string into a time."""
    parts = [int(p) for p in str(value).split(":")]
    while len(parts) < 3:
        parts.append(0)
    return time(parts[0], parts[1], parts[2])


@dataclass
class ResyAuth:
    api_key: str
    auth_token: str
    payment_method_id: int = 0
    dry_run: bool = True


@dataclass
class Target:
    """A restaurant reservation target, shared by sniper and watcher."""

    name: str
    venue_id: int
    party_size: int
    preferred_times: list[time] = field(default_factory=list)
    time_window: tuple[time, time] | None = None
    table_types: list[str] = field(default_factory=list)
    timezone: str = "America/New_York"

    # Sniper-only
    drop_time: time | None = None
    drop_days_ahead: int | None = None

    # Watcher-only
    poll_interval: float = 15.0

    # Resolved or pinned reservation date.
    date: date_cls | None = None

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def resolved_date(self, now: datetime | None = None) -> date_cls:
        """The reservation date to search for.

        Pinned `date` wins; otherwise derive from the drop date + days_ahead.
        """
        if self.date is not None:
            return self.date
        if self.drop_days_ahead is not None:
            base = (now or datetime.now(self.tz)).date()
            return base + timedelta(days=self.drop_days_ahead)
        raise ValueError(f"Target {self.name!r} has neither `date` nor `drop_days_ahead`")

    def next_drop_datetime(self, now: datetime | None = None) -> datetime:
        """The next wall-clock moment this target's tables drop (tz-aware)."""
        if self.drop_time is None:
            raise ValueError(f"Target {self.name!r} has no `drop_time`")
        now = now or datetime.now(self.tz)
        candidate = datetime.combine(now.date(), self.drop_time, tzinfo=self.tz)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate


@dataclass
class Config:
    auth: ResyAuth
    snipe: list[Target] = field(default_factory=list)
    watchlist: list[Target] = field(default_factory=list)


def _build_target(raw: dict, defaults: dict) -> Target:
    party_size = raw.get("party_size", defaults.get("party_size", 2))
    timezone = raw.get("timezone", defaults.get("timezone", "America/New_York"))

    window = raw.get("time_window")
    time_window = (
        (_parse_time(window[0]), _parse_time(window[1])) if window else None
    )

    date_val = raw.get("date")
    parsed_date = (
        date_val
        if isinstance(date_val, date_cls)
        else (datetime.strptime(date_val, "%Y-%m-%d").date() if date_val else None)
    )

    return Target(
        name=raw["name"],
        venue_id=int(raw["venue_id"]),
        party_size=int(party_size),
        preferred_times=[_parse_time(t) for t in raw.get("preferred_times", [])],
        time_window=time_window,
        table_types=list(raw.get("table_types", [])),
        timezone=timezone,
        drop_time=_parse_time(raw["drop_time"]) if raw.get("drop_time") else None,
        drop_days_ahead=raw.get("drop_days_ahead"),
        poll_interval=float(raw.get("poll_interval", 15.0)),
        date=parsed_date,
    )


def load_config(path: str | Path) -> Config:
    path = Path(path)
    with path.open() as fh:
        raw = yaml.safe_load(fh)

    resy = raw.get("resy", {})
    auth = ResyAuth(
        api_key=resy["api_key"],
        auth_token=resy["auth_token"],
        payment_method_id=int(resy.get("payment_method_id", 0)),
        dry_run=bool(resy.get("dry_run", True)),
    )

    defaults = raw.get("defaults", {})
    snipe = [_build_target(t, defaults) for t in raw.get("snipe", []) or []]
    watchlist = [_build_target(t, defaults) for t in raw.get("watchlist", []) or []]

    return Config(auth=auth, snipe=snipe, watchlist=watchlist)
