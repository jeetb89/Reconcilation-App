"""Differential test: at every step of a multi-day scenario, the
incremental run's stored result must exactly match what an independent,
from-scratch full rescan of the pure reconcile() would produce. This is
the actual correctness guarantee the incremental optimization needs --
"faster" is worthless if it's not "identical."
"""

from app.core.reconcile import reconcile
from app.models import ManualMatch, RunResultItem, SourceRecord, UnmatchedAck, db
from app.services.converters import to_canonical
from app.services.ingest import ingest_file
from app.services.run_service import run_reconciliation


def _full_rescan_snapshot():
    """Ground truth: run the pure matcher over literally everything
    currently in the database, bypassing the incremental machinery."""
    ledger_rows = SourceRecord.query.filter_by(source_system="LEDGER").all()
    statement_rows = SourceRecord.query.filter_by(source_system="STATEMENT").all()

    manual_matches = {
        (mm.ledger_record.external_ref, mm.statement_record.external_ref)
        for mm in ManualMatch.query.all()
    }
    acks = {
        (ack.source_record.source_system, ack.source_record.external_ref)
        for ack in UnmatchedAck.query.all()
    }

    result = reconcile(
        [to_canonical(r) for r in ledger_rows],
        [to_canonical(r) for r in statement_rows],
        manual_matches=manual_matches,
        acknowledged_unmatched=acks,
    )

    ok = {(p.ledger.external_ref, p.statement.external_ref) for p in result.matched if p.status == "OK"}
    breaks = {(p.ledger.external_ref, p.statement.external_ref) for p in result.matched if p.status == "BREAK"}
    unmatched_l = {r.external_ref for r in result.unmatched_ledger}
    unmatched_s = {r.external_ref for r in result.unmatched_statement}
    return ok, breaks, unmatched_l, unmatched_s


def _incremental_snapshot(run):
    items = RunResultItem.query.filter_by(run_id=run.id).all()
    ok, breaks, unmatched_l, unmatched_s = set(), set(), set(), set()
    for i in items:
        if i.bucket == "OK":
            ok.add((i.ledger_record.external_ref, i.statement_record.external_ref))
        elif i.bucket == "BREAK":
            breaks.add((i.ledger_record.external_ref, i.statement_record.external_ref))
        elif i.bucket == "UNMATCHED_LEDGER":
            unmatched_l.add(i.ledger_record.external_ref)
        elif i.bucket == "UNMATCHED_STATEMENT":
            unmatched_s.add(i.statement_record.external_ref)
    return ok, breaks, unmatched_l, unmatched_s


def _assert_matches_full_rescan(run):
    assert _incremental_snapshot(run) == _full_rescan_snapshot()


def _rec(source_system, ref):
    return SourceRecord.query.filter_by(source_system=source_system, external_ref=ref).first()


def test_incremental_run_matches_full_rescan_across_a_multi_day_scenario(app):
    # Day 1: initial load, a mix of clean matches, a break, and orphans on
    # both sides.
    ingest_file("LEDGER", "l1.csv", (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01T09:20:00Z,ETH-USD,BUY,10,3400,34000.00,SETTLED\n"
        b"T-3,2025-07-01T09:25:00Z,SOL-USD,SELL,300,146,43800.00,SETTLED\n"
        b"T-4,2025-07-01T09:30:00Z,BTC-USD,BUY,0.1,64000,6400.00,SETTLED\n"
        b"T-5,2025-07-01T09:35:00Z,ETH-USD,SELL,2,3400,6800.00,CANCELLED\n"
    ))
    ingest_file("STATEMENT", "s1.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01 09:20:00,ETH-USD,B,10,3400,34000.00,SETTLED\n"
        b"T-3,2025-07-01 09:25:00,SOL-USD,S,300,148,44400.00,SETTLED\n"
        b"C-9,2025-07-01 09:50:00,ETH-USD,B,2,3400,6800.00,SETTLED\n"
    ))
    run1 = run_reconciliation()
    _assert_matches_full_rescan(run1)
    assert run1.ok_count == 2       # T-1, T-2
    assert run1.break_count == 1    # T-3
    assert run1.unmatched_ledger_count == 1     # T-4
    assert run1.unmatched_statement_count == 1  # C-9

    # Day 2: correction fixes the T-3 break; nothing else changes.
    ingest_file("STATEMENT", "s1_corrected.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01 09:20:00,ETH-USD,B,10,3400,34000.00,SETTLED\n"
        b"T-3,2025-07-01 09:25:00,SOL-USD,S,300,146,43800.00,SETTLED\n"
        b"C-9,2025-07-01 09:50:00,ETH-USD,B,2,3400,6800.00,SETTLED\n"
    ))
    run2 = run_reconciliation()
    _assert_matches_full_rescan(run2)
    assert run2.ok_count == 3
    assert run2.break_count == 0

    # Day 3: a human manually pairs T-4 (ledger-only) with C-9
    # (statement-only) -- different reference schemes, same trade.
    db.session.add(ManualMatch(ledger_record_id=_rec("LEDGER", "T-4").id, statement_record_id=_rec("STATEMENT", "C-9").id))
    db.session.commit()
    run3 = run_reconciliation()
    _assert_matches_full_rescan(run3)
    assert run3.unmatched_ledger_count == 0
    assert run3.unmatched_statement_count == 0

    # Day 4: a new ledger trade arrives with no counterpart yet, and a human
    # acknowledges it has none (for now).
    ingest_file("LEDGER", "l2.csv", (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01T09:20:00Z,ETH-USD,BUY,10,3400,34000.00,SETTLED\n"
        b"T-3,2025-07-01T09:25:00Z,SOL-USD,SELL,300,146,43800.00,SETTLED\n"
        b"T-4,2025-07-01T09:30:00Z,BTC-USD,BUY,0.1,64000,6400.00,SETTLED\n"
        b"T-5,2025-07-01T09:35:00Z,ETH-USD,SELL,2,3400,6800.00,CANCELLED\n"
        b"T-6,2025-07-02T10:00:00Z,SOL-USD,BUY,20,150,3000.00,SETTLED\n"
    ))
    run4 = run_reconciliation()
    _assert_matches_full_rescan(run4)
    assert run4.unmatched_ledger_count == 1  # T-6

    db.session.add(UnmatchedAck(source_record_id=_rec("LEDGER", "T-6").id))
    db.session.commit()
    run5 = run_reconciliation()
    _assert_matches_full_rescan(run5)
    assert run5.unmatched_ledger_count == 0

    # Day 5: T-6's real counterpart finally arrives -- the earlier ack must
    # not have permanently hidden it from ever matching.
    ingest_file("STATEMENT", "s2.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01 09:20:00,ETH-USD,B,10,3400,34000.00,SETTLED\n"
        b"T-3,2025-07-01 09:25:00,SOL-USD,S,300,146,43800.00,SETTLED\n"
        b"C-9,2025-07-01 09:50:00,ETH-USD,B,2,3400,6800.00,SETTLED\n"
        b"T-6,2025-07-02 10:00:00,SOL-USD,B,20,150,3000.00,SETTLED\n"
    ))
    run6 = run_reconciliation()
    _assert_matches_full_rescan(run6)
    assert run6.unmatched_ledger_count == 0
    assert run6.unmatched_statement_count == 0
    # T-1, T-2, T-3, T-6 all auto-match cleanly. T-4/C-9 is the manual pair
    # from Day 3 -- their fields genuinely differ (different instrument, qty,
    # amount), so that pairing is correctly a BREAK, not OK.
    assert run6.ok_count == 4
    assert run6.break_count == 1
