"""Canonical shape both source formats normalize into. No DB, no framework imports here."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class CanonicalRecord:
    source_system: str      # e.g. "LEDGER", "STATEMENT" -- open-ended, a third source just adds a new value
    external_ref: str       # normalized trade identifier used to join the two sides
    executed_at: datetime   # normalized to UTC
    instrument: str
    side: str               # normalized to "BUY" / "SELL"
    quantity: Decimal
    price: Decimal
    amount: Decimal
    status: str             # normalized to "SETTLED" / "CANCELLED" / "PENDING" / ...
    raw: dict = field(default_factory=dict)   # original row, kept for the UI / audit trail
