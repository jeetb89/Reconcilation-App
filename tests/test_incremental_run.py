"""The second (and later) run must only recompute records that changed,
or that could plausibly newly match something, and carry everything else
forward untouched -- but the *output* must be identical to what a full
rescan would have produced. These tests check outcomes, not internals.
"""

from app.models import ManualMatch, RunResultItem, SourceRecord, UnmatchedAck, db
from app.services.ingest import ingest_file
from app.services.run_service import run_reconciliation


def _rec(source_system, ref):
    return SourceRecord.query.filter_by(source_system=source_system, external_ref=ref).first()


def test_untouched_matched_pair_is_carried_forward_unchanged(app):
    ingest_file("LEDGER", "l1.csv", (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
    ))
    ingest_file("STATEMENT", "s1.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
    ))
    run1 = run_reconciliation()
    assert run1.ok_count == 1

    # nothing changes at all between runs
    run2 = run_reconciliation()
    assert run2.ok_count == 1
    assert run2.break_count == 0

    items = RunResultItem.query.filter_by(run_id=run2.id).all()
    assert len(items) == 1
    assert items[0].bucket == "OK"


def test_correction_to_a_previously_ok_pair_flips_it_to_break(app):
    ledger_csv = (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
    )
    ingest_file("LEDGER", "l1.csv", ledger_csv)
    ingest_file("STATEMENT", "s1.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
    ))
    run1 = run_reconciliation()
    assert run1.ok_count == 1

    # correction: ledger amount now genuinely diverges from the statement
    corrected = ledger_csv.replace(b"31000.00", b"25000.00")
    ingest_file("LEDGER", "l1_corrected.csv", corrected)

    run2 = run_reconciliation()
    assert run2.ok_count == 0
    assert run2.break_count == 1

    items = RunResultItem.query.filter_by(run_id=run2.id, bucket="BREAK").all()
    assert len(items) == 1
    assert "amount" in items[0].diffs_json


def test_new_upload_correctly_matches_a_previously_unmatched_row(app):
    ingest_file("LEDGER", "l1.csv", (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
    ))
    run1 = run_reconciliation()
    assert run1.unmatched_ledger_count == 1

    # statement side arrives later, in a second run
    ingest_file("STATEMENT", "s1.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
    ))
    run2 = run_reconciliation()
    assert run2.ok_count == 1
    assert run2.unmatched_ledger_count == 0


def test_acknowledged_row_still_matches_a_later_genuine_counterpart(app):
    ingest_file("LEDGER", "l1.csv", (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
    ))
    run1 = run_reconciliation()
    assert run1.unmatched_ledger_count == 1

    # a human accepts it has no pair -- yet
    t1 = _rec("LEDGER", "T-1")
    db.session.add(UnmatchedAck(source_record_id=t1.id))
    db.session.commit()

    run2 = run_reconciliation()
    assert run2.unmatched_ledger_count == 0  # suppressed by the ack

    # its real counterpart shows up two runs later -- the ack must not
    # permanently hide this row from ever being matched again
    ingest_file("STATEMENT", "s1.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
    ))
    run3 = run_reconciliation()
    assert run3.ok_count == 1
    assert run3.unmatched_ledger_count == 0
    assert run3.unmatched_statement_count == 0


def test_manual_match_made_between_runs_is_picked_up_next_run(app):
    ingest_file("LEDGER", "l1.csv", (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
    ))
    ingest_file("STATEMENT", "s1.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"C-9,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
    ))
    run1 = run_reconciliation()
    assert run1.unmatched_ledger_count == 1
    assert run1.unmatched_statement_count == 1

    t1, c9 = _rec("LEDGER", "T-1"), _rec("STATEMENT", "C-9")
    db.session.add(ManualMatch(ledger_record_id=t1.id, statement_record_id=c9.id))
    db.session.commit()

    run2 = run_reconciliation()
    assert run2.ok_count == 1
    assert run2.unmatched_ledger_count == 0
    assert run2.unmatched_statement_count == 0


def test_three_runs_where_only_one_pair_ever_changes(app):
    # a second, completely untouched pair should carry forward across
    # every subsequent run without being recomputed
    ingest_file("LEDGER", "l1.csv", (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01T09:20:00Z,ETH-USD,BUY,10,3400,34000.00,SETTLED\n"
    ))
    ledger_t2_csv = (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01T09:20:00Z,ETH-USD,BUY,10,3400,34000.00,SETTLED\n"
    )
    ingest_file("STATEMENT", "s1.csv", (
        b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01 09:20:00,ETH-USD,B,10,3400,34000.00,SETTLED\n"
    ))
    run1 = run_reconciliation()
    assert run1.ok_count == 2

    run2 = run_reconciliation()  # nothing changes
    assert run2.ok_count == 2

    # only T-1 gets corrected into a break; T-2 must remain OK, carried forward
    corrected = ledger_t2_csv.replace(b"31000.00", b"1.00")
    ingest_file("LEDGER", "l1_corrected.csv", corrected)
    run3 = run_reconciliation()
    assert run3.ok_count == 1
    assert run3.break_count == 1

    ok_items = RunResultItem.query.filter_by(run_id=run3.id, bucket="OK").all()
    assert len(ok_items) == 1
    assert ok_items[0].ledger_record.external_ref == "T-2"
