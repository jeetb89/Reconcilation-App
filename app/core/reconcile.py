"""Matching + comparison. Pure functions: lists of CanonicalRecord in, a
ReconciliationResult out. No DB, no HTTP -- this is what the tests exercise
directly.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from app.core.records import CanonicalRecord

# Tolerances: rounding/fees and clock drift are expected and NOT breaks.
# Amount is "within tolerance" if it passes EITHER check (absolute or relative),
# since a flat fee dominates on small trades and a percentage drift dominates on large ones.
AMOUNT_ABS_TOLERANCE = Decimal("1.00")
AMOUNT_PCT_TOLERANCE = Decimal("0.001")  # 0.1%
TIME_TOLERANCE = timedelta(minutes=30)


@dataclass(frozen=True)
class FieldDiff:
    field: str
    ledger_value: object
    statement_value: object
    delta: Optional[object] = None


@dataclass(frozen=True)
class MatchedPair:
    ledger: CanonicalRecord
    statement: CanonicalRecord
    match_type: str  # "AUTO" or "MANUAL"
    diffs: tuple = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "BREAK" if self.diffs else "OK"


@dataclass(frozen=True)
class ReconciliationResult:
    matched: tuple  # tuple[MatchedPair, ...]
    unmatched_ledger: tuple  # tuple[CanonicalRecord, ...]
    unmatched_statement: tuple  # tuple[CanonicalRecord, ...]


def compare_pair(ledger: CanonicalRecord, statement: CanonicalRecord) -> tuple:
    """Field-by-field diff. Returns a tuple of FieldDiff -- empty means OK."""
    diffs = []

    if ledger.instrument != statement.instrument:
        diffs.append(FieldDiff("instrument", ledger.instrument, statement.instrument))

    if ledger.side != statement.side:
        diffs.append(FieldDiff("side", ledger.side, statement.side))

    if ledger.quantity != statement.quantity:
        diffs.append(FieldDiff(
            "quantity", ledger.quantity, statement.quantity,
            delta=ledger.quantity - statement.quantity,
        ))

    if ledger.status != statement.status:
        diffs.append(FieldDiff("status", ledger.status, statement.status))

    amount_delta = ledger.amount - statement.amount
    within_abs = abs(amount_delta) <= AMOUNT_ABS_TOLERANCE
    largest = max(abs(ledger.amount), abs(statement.amount)) or Decimal("1")
    within_pct = abs(amount_delta) / largest <= AMOUNT_PCT_TOLERANCE
    if not (within_abs or within_pct):
        diffs.append(FieldDiff("amount", ledger.amount, statement.amount, delta=amount_delta))

    time_delta = ledger.executed_at - statement.executed_at
    if abs(time_delta) > TIME_TOLERANCE:
        diffs.append(FieldDiff(
            "executed_at", ledger.executed_at.isoformat(), statement.executed_at.isoformat(),
            delta=str(time_delta),
        ))

    return tuple(diffs)


def reconcile(
    ledger_records,
    statement_records,
    manual_matches=frozenset(),      # {(ledger_ref, statement_ref), ...}
    acknowledged_unmatched=frozenset(),  # {("LEDGER", ref), ("STATEMENT", ref), ...}
) -> ReconciliationResult:
    """Cancelled trades are excluded before matching -- they were never meant
    to be compared. Manual matches (human-paired rows the auto-matcher missed)
    are applied before deciding what's left unmatched. Acknowledged-unmatched
    rows are dropped from the unmatched buckets so they stop resurfacing.
    """
    ledger_live = {r.external_ref: r for r in ledger_records if r.status != "CANCELLED"}
    statement_live = {r.external_ref: r for r in statement_records if r.status != "CANCELLED"}

    matched = []

    # 1. Auto-match: same reference on both sides.
    auto_refs = set(ledger_live) & set(statement_live)
    for ref in auto_refs:
        l, s = ledger_live.pop(ref), statement_live.pop(ref)
        matched.append(MatchedPair(l, s, match_type="AUTO", diffs=compare_pair(l, s)))

    # 2. Manual matches: human-paired rows the auto-matcher couldn't join
    #    (e.g. references genuinely differ between the two sources).
    for ledger_ref, statement_ref in manual_matches:
        l = ledger_live.pop(ledger_ref, None)
        s = statement_live.pop(statement_ref, None)
        if l is not None and s is not None:
            matched.append(MatchedPair(l, s, match_type="MANUAL", diffs=compare_pair(l, s)))

    # 3. Whatever's left is unmatched, minus rows a human already acknowledged.
    unmatched_ledger = tuple(
        r for ref, r in ledger_live.items() if ("LEDGER", ref) not in acknowledged_unmatched
    )
    unmatched_statement = tuple(
        r for ref, r in statement_live.items() if ("STATEMENT", ref) not in acknowledged_unmatched
    )

    return ReconciliationResult(
        matched=tuple(matched),
        unmatched_ledger=unmatched_ledger,
        unmatched_statement=unmatched_statement,
    )
