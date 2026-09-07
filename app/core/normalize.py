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


def _column(row, name):
    """Fetch a required column, turning a missing/blank header into a
    NormalizationError instead of an unhandled KeyError -- this is what a
    wrong source-system selection (or a file in the wrong format) hits."""
    value = row.get(name)
    if value is None:
        raise NormalizationError(f"missing column {name!r} -- is this the right file/source?")
    return value


def normalize_ledger_row(row: dict) -> CanonicalRecord:
    """Our own ledger: trade_id,traded_at,instrument,side,quantity,price,gross_amount,state"""
    traded_at = _column(row, "traded_at").strip()
    try:
        # ISO 8601 with trailing Z, e.g. 2025-07-01T09:15:00Z
        dt = datetime.fromisoformat(traded_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        raise NormalizationError(f"bad traded_at: {traded_at!r}")

    return CanonicalRecord(
        source_system="LEDGER",
        external_ref=_normalize_ref(_column(row, "trade_id")),
        executed_at=dt,
        instrument=_column(row, "instrument").strip().upper(),
        side=_normalize_side(_column(row, "side")),
        quantity=_to_decimal(_column(row, "quantity"), "quantity"),
        price=_to_decimal(_column(row, "price"), "price"),
        amount=_to_decimal(_column(row, "gross_amount"), "gross_amount"),
        status=_normalize_status(_column(row, "state")),
        raw=dict(row),
    )


def normalize_statement_row(row: dict) -> CanonicalRecord:
    """The other company's statement: reference,executed_at,symbol,direction,qty,unit_price,total,status"""
    executed_at = _column(row, "executed_at").strip()
    try:
        # space-separated, no timezone marker -- assume UTC (documented in README)
        dt = datetime.strptime(executed_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        raise NormalizationError(f"bad executed_at: {executed_at!r}")

    return CanonicalRecord(
        source_system="STATEMENT",
        external_ref=_normalize_ref(_column(row, "reference")),
        executed_at=dt,
        instrument=_column(row, "symbol").strip().upper(),
        side=_normalize_side(_column(row, "direction"), "direction"),
        quantity=_to_decimal(_column(row, "qty"), "qty"),
        price=_to_decimal(_column(row, "unit_price"), "unit_price"),
        amount=_to_decimal(_column(row, "total"), "total"),
        status=_normalize_status(_column(row, "status")),
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
