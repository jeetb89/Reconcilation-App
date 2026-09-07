from app.models import ManualMatch, SourceRecord, SourceRecordHistory, UnmatchedAck
from app.services.ingest import ingest_file
from app.services.run_service import run_reconciliation

LEDGER_CSV = (
    b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
    b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
    b"T-2,2025-07-01T09:20:00Z,ETH-USD,BUY,10,3400,34000.00,SETTLED\n"
    b"T-3,2025-07-01T09:25:00Z,SOL-USD,BUY,1,149,149.00,CANCELLED\n"
)
STATEMENT_CSV = (
    b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
    b"T-1,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
    b"C-9,2025-07-01 09:50:00,ETH-USD,B,2,3400,6800.00,SETTLED\n"
)


def test_ingest_then_run_end_to_end(app):
    ingest_file("LEDGER", "ledger.csv", LEDGER_CSV)
    ingest_file("STATEMENT", "statement.csv", STATEMENT_CSV)

    run = run_reconciliation()

    assert run.ok_count == 1          # T-1 matches exactly
    assert run.break_count == 0
    assert run.unmatched_ledger_count == 1   # T-2 has no statement counterpart
    assert run.unmatched_statement_count == 1  # C-9 has no ledger counterpart
    # T-3 is CANCELLED -- never counted anywhere
    assert run.ok_count + run.break_count + run.unmatched_ledger_count + run.unmatched_statement_count == 3


def test_reuploading_identical_file_is_a_noop(app):
    r1 = ingest_file("LEDGER", "ledger.csv", LEDGER_CSV)
    r2 = ingest_file("LEDGER", "ledger.csv", LEDGER_CSV)
    assert not r1.skipped_duplicate_file
    assert r2.skipped_duplicate_file
    assert SourceRecord.query.count() == 3  # not duplicated


def test_correction_file_updates_record_and_archives_history(app):
    ingest_file("LEDGER", "ledger.csv", LEDGER_CSV)

    corrected = LEDGER_CSV.replace(b"31000.00", b"30990.00")
    result = ingest_file("LEDGER", "ledger_corrected.csv", corrected)

    assert result.rows_updated == 1
    assert result.rows_unchanged == 2

    rec = SourceRecord.query.filter_by(source_system="LEDGER", external_ref="T-1").first()
    assert str(rec.amount) == "30990.00000000"

    history = SourceRecordHistory.query.filter_by(source_record_id=rec.id).first()
    assert str(history.amount) == "31000.00000000"  # old value preserved


def test_manual_match_and_ack_persist_across_runs(app):
    ingest_file("LEDGER", "ledger.csv", LEDGER_CSV)
    ingest_file("STATEMENT", "statement.csv", STATEMENT_CSV)

    t2 = SourceRecord.query.filter_by(source_system="LEDGER", external_ref="T-2").first()
    c9 = SourceRecord.query.filter_by(source_system="STATEMENT", external_ref="C-9").first()

    from app.models import db
    db.session.add(ManualMatch(ledger_record_id=t2.id, statement_record_id=c9.id))
    db.session.commit()

    run = run_reconciliation()
    assert run.unmatched_ledger_count == 0
    assert run.unmatched_statement_count == 0
    # T-1 auto-matches OK; T-2/C-9 is a manual pairing whose fields genuinely
    # differ (qty 10 vs 2), so it's a BREAK -- manual matching resolves *which*
    # rows correspond, not whether their values agree.
    assert run.ok_count == 1
    assert run.break_count == 1
