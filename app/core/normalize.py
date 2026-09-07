"""Source-format adapters: raw CSV row (dict) -> CanonicalRecord.

Adding a third company's format later means writing one more `normalize_*_row`
function and registering it in ADAPTERS -- nothing downstream changes.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.core.records import CanonicalRecord

SIDE_MAP = {
    "BUY": "BUY", "B": "BUY",
    "SELL": "SELL", "S": "SELL",
}

STATUS_MAP = {
    "SETTLED": "SETTLED",
    "CANCELLED": "CANCELLED",
    "CANCELED": "CANCELLED",
    "PENDING": "PENDING",
}


class NormalizationError(ValueError):
    """Raised when a raw row can't be turned into a CanonicalRecord."""


def _to_decimal(value, field_name):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise NormalizationError(f"bad decimal for {field_name!r}: {value!r}")


def _normalize_side(value, field_name="side"):
    key = str(value).strip().upper()
    if key not in SIDE_MAP:
        raise NormalizationError(f"unrecognized {field_name}: {value!r}")
    return SIDE_MAP[key]


def _normalize_status(value):
    key = str(value).strip().upper()
    if key not in STATUS_MAP:
        raise NormalizationError(f"unrecognized status: {value!r}")
    return STATUS_MAP[key]


def _normalize_ref(value):
    return str(value).strip().upper()


def normalize_ledger_row(row: dict) -> CanonicalRecord:
    """Our own ledger: trade_id,traded_at,instrument,side,quantity,price,gross_amount,state"""
    traded_at = row["traded_at"].strip()
    # ISO 8601 with trailing Z, e.g. 2025-07-01T09:15:00Z
    dt = datetime.fromisoformat(traded_at.replace("Z", "+00:00")).astimezone(timezone.utc)

    return CanonicalRecord(
        source_system="LEDGER",
        external_ref=_normalize_ref(row["trade_id"]),
        executed_at=dt,
        instrument=row["instrument"].strip().upper(),
        side=_normalize_side(row["side"]),
        quantity=_to_decimal(row["quantity"], "quantity"),
        price=_to_decimal(row["price"], "price"),
        amount=_to_decimal(row["gross_amount"], "gross_amount"),
        status=_normalize_status(row["state"]),
        raw=dict(row),
    )


def normalize_statement_row(row: dict) -> CanonicalRecord:
    """The other company's statement: reference,executed_at,symbol,direction,qty,unit_price,total,status"""
    executed_at = row["executed_at"].strip()
    # space-separated, no timezone marker -- assume UTC (documented in README)
    dt = datetime.strptime(executed_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    return CanonicalRecord(
        source_system="STATEMENT",
        external_ref=_normalize_ref(row["reference"]),
        executed_at=dt,
        instrument=row["symbol"].strip().upper(),
        side=_normalize_side(row["direction"], "direction"),
        quantity=_to_decimal(row["qty"], "qty"),
        price=_to_decimal(row["unit_price"], "unit_price"),
        amount=_to_decimal(row["total"], "total"),
        status=_normalize_status(row["status"]),
        raw=dict(row),
    )


ADAPTERS = {
    "LEDGER": normalize_ledger_row,
    "STATEMENT": normalize_statement_row,
}


def normalize_row(source_system: str, row: dict) -> CanonicalRecord:
    try:
        adapter = ADAPTERS[source_system]
    except KeyError:
        raise NormalizationError(f"no adapter registered for source {source_system!r}")
    return adapter(row)
