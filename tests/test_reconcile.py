from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.records import CanonicalRecord
from app.core.reconcile import reconcile


def make(source, ref, **overrides):
    defaults = dict(
        source_system=source,
        external_ref=ref,
        executed_at=datetime(2025, 7, 1, 9, 15, 0, tzinfo=timezone.utc),
        instrument="BTC-USD",
        side="BUY",
        quantity=Decimal("1"),
        price=Decimal("100"),
        amount=Decimal("100"),
        status="SETTLED",
        raw={},
    )
    defaults.update(overrides)
    return CanonicalRecord(**defaults)


def test_exact_match_is_ok():
    l = make("LEDGER", "T-1")
    s = make("STATEMENT", "T-1")
    result = reconcile([l], [s])
    assert len(result.matched) == 1
    assert result.matched[0].status == "OK"
    assert result.matched[0].match_type == "AUTO"
    assert not result.unmatched_ledger
    assert not result.unmatched_statement


def test_small_amount_drift_is_ok_rounding_and_fees():
    l = make("LEDGER", "T-1", amount=Decimal("31000.00"))
    s = make("STATEMENT", "T-1", amount=Decimal("31000.50"))  # 50c fee-sized drift
    result = reconcile([l], [s])
    assert result.matched[0].status == "OK"


def test_large_amount_drift_is_a_break():
    l = make("LEDGER", "T-1", amount=Decimal("34000.00"))
    s = make("STATEMENT", "T-1", amount=Decimal("34170.00"))  # ~0.5% off, real price discrepancy
    result = reconcile([l], [s])
    pair = result.matched[0]
    assert pair.status == "BREAK"
    fields = {d.field for d in pair.diffs}
    assert "amount" in fields


def test_small_time_drift_is_ok_clock_skew():
    l = make("LEDGER", "T-1", executed_at=datetime(2025, 7, 1, 9, 15, 0, tzinfo=timezone.utc))
    s = make("STATEMENT", "T-1", executed_at=datetime(2025, 7, 1, 9, 16, 0, tzinfo=timezone.utc))
    result = reconcile([l], [s])
    assert result.matched[0].status == "OK"


def test_large_time_drift_is_a_break():
    l = make("LEDGER", "T-1", executed_at=datetime(2025, 7, 1, 9, 15, 0, tzinfo=timezone.utc))
    s = make("STATEMENT", "T-1", executed_at=datetime(2025, 7, 1, 11, 15, 0, tzinfo=timezone.utc))
    result = reconcile([l], [s])
    pair = result.matched[0]
    assert pair.status == "BREAK"
    assert any(d.field == "executed_at" for d in pair.diffs)


def test_side_mismatch_is_a_break():
    l = make("LEDGER", "T-1", side="BUY")
    s = make("STATEMENT", "T-1", side="SELL")
    result = reconcile([l], [s])
    assert result.matched[0].status == "BREAK"
    assert any(d.field == "side" for d in result.matched[0].diffs)


def test_ledger_only_row_is_unmatched():
    l = make("LEDGER", "T-1")
    result = reconcile([l], [])
    assert not result.matched
    assert result.unmatched_ledger == (l,)
    assert not result.unmatched_statement


def test_statement_only_row_is_unmatched():
    s = make("STATEMENT", "T-9")
    result = reconcile([], [s])
    assert result.unmatched_statement == (s,)


def test_cancelled_rows_are_excluded_entirely():
    l = make("LEDGER", "T-1", status="CANCELLED")
    result = reconcile([l], [])
    assert not result.matched
    assert not result.unmatched_ledger  # never surfaced -- cancelled trades aren't compared at all


def test_manual_match_pairs_rows_with_different_references():
    l = make("LEDGER", "T-1")
    s = make("STATEMENT", "C-9001")
    result = reconcile([l], [s], manual_matches={("T-1", "C-9001")})
    assert len(result.matched) == 1
    assert result.matched[0].match_type == "MANUAL"
    assert not result.unmatched_ledger
    assert not result.unmatched_statement


def test_acknowledged_unmatched_row_is_suppressed():
    l = make("LEDGER", "T-1")
    result = reconcile([l], [], acknowledged_unmatched={("LEDGER", "T-1")})
    assert not result.unmatched_ledger


def test_manual_match_survives_alongside_unrelated_unmatched_rows():
    matched_l = make("LEDGER", "T-1")
    matched_s = make("STATEMENT", "C-1")
    stray_l = make("LEDGER", "T-2")
    result = reconcile([matched_l, stray_l], [matched_s], manual_matches={("T-1", "C-1")})
    assert len(result.matched) == 1
    assert result.unmatched_ledger == (stray_l,)
