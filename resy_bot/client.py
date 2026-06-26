"""Async client for the (unofficial) Resy HTTP API.

Endpoints used:
  GET  /4/find      -> list bookable slots for a venue/day/party_size
  POST /3/details   -> exchange a slot's config token for a book_token
  POST /3/book      -> commit the reservation
  GET  /2/user      -> account info (used to discover payment_method_id)

These are the same calls resy.com makes in the browser. They are not an
official, supported API and may change without notice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_cls

import httpx

log = logging.getLogger("resy_bot.client")

BASE_URL = "https://api.resy.com"


@dataclass
class Slot:
    """A single bookable time slot returned by /4/find."""

    config_token: str       # opaque token passed to /3/details
    table_type: str         # e.g. "Dining Room", "Bar", "Patio"
    start: str              # "YYYY-MM-DD HH:MM:00" (venue-local)

    @property
    def clock(self) -> str:
        """The "HH:MM" portion of the slot start time."""
        return self.start.split(" ")[1][:5] if " " in self.start else self.start

    @classmethod
    def from_api(cls, raw: dict) -> "Slot":
        config = raw.get("config", {})
        return cls(
            config_token=config.get("token", ""),
            table_type=config.get("type", ""),
            start=raw.get("date", {}).get("start", ""),
        )


class BookingError(RuntimeError):
    """Raised when a booking attempt fails for an expected reason."""


class ResyClient:
    def __init__(
        self,
        api_key: str,
        auth_token: str,
        payment_method_id: int = 0,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.auth_token = auth_token
        self.payment_method_id = payment_method_id
        # A keep-alive client so the TLS/TCP handshake is already paid for when
        # the drop lands — this matters for sniping latency.
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            headers=self._headers(),
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=60),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f'ResyAPI api_key="{self.api_key}"',
            "X-Resy-Auth-Token": self.auth_token,
            "X-Resy-Universal-Auth": self.auth_token,
            "Origin": "https://resy.com",
            "Referer": "https://resy.com/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "ResyClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def find_slots(
        self, venue_id: int, day: date_cls, party_size: int
    ) -> list[Slot]:
        """Return all bookable slots for a venue on a given day."""
        params = {
            "lat": "0",
            "long": "0",
            "day": day.isoformat(),
            "party_size": str(party_size),
            "venue_id": str(venue_id),
        }
        resp = await self._client.get("/4/find", params=params)
        resp.raise_for_status()
        data = resp.json()
        venues = data.get("results", {}).get("venues", [])
        if not venues:
            return []
        return [Slot.from_api(s) for s in venues[0].get("slots", [])]

    async def get_book_token(
        self, config_token: str, day: date_cls, party_size: int
    ) -> str:
        """Exchange a slot config token for a (short-lived) book_token."""
        payload = {
            "config_id": config_token,
            "day": day.isoformat(),
            "party_size": party_size,
        }
        resp = await self._client.post("/3/details", json=payload)
        resp.raise_for_status()
        data = resp.json()
        token = data.get("book_token", {}).get("value")
        if not token:
            raise BookingError(f"No book_token in details response: {data}")
        return token

    async def book(self, book_token: str) -> dict:
        """Commit a reservation. Returns the booking confirmation payload."""
        if not self.payment_method_id:
            raise BookingError(
                "payment_method_id is not set; cannot book. "
                "Fill it in config.yaml (see README)."
            )
        data = {
            "book_token": book_token,
            "struct_payment_method": '{"id":%d}' % self.payment_method_id,
            "source_id": "resy.com-venue-details",
        }
        resp = await self._client.post(
            "/3/book",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code >= 400:
            raise BookingError(
                f"Book failed ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    async def get_user(self) -> dict:
        """Account info — handy for discovering your payment_method_id."""
        resp = await self._client.get("/2/user")
        resp.raise_for_status()
        return resp.json()
