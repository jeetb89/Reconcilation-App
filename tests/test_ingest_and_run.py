import pytest

from app.models import ManualMatch, SourceFile, SourceRecord, SourceRecordHistory, UnmatchedAck
from app.services.ingest import FileFormatError, ingest_file
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


def test_ingest_rejects_empty_file(app):
    with pytest.raises(FileFormatError):
        ingest_file("LEDGER", "empty.csv", b"")
    assert SourceFile.query.count() == 0  # nothing half-created


def test_ingest_rejects_non_utf8_bytes(app):
    garbage = b"\xff\xfe\x00\x01not text"
    with pytest.raises(FileFormatError):
        ingest_file("LEDGER", "garbage.bin", garbage)
    assert SourceFile.query.count() == 0


def test_ingest_rejects_file_with_no_header_row(app):
    # a CSV library sees an empty file body as having no header at all
    with pytest.raises(FileFormatError):
        ingest_file("LEDGER", "no_header.csv", b"\n\n\n")
    assert SourceFile.query.count() == 0


def test_ingest_skips_blank_lines_without_error(app):
    # csv.DictReader drops genuinely blank lines on its own -- nothing to
    # reject, and it must not throw off inserted/error counts.
    csv_with_blank_line = (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
        b"\n"
        b"T-2,2025-07-01T09:20:00Z,ETH-USD,BUY,10,3400,34000.00,SETTLED\n"
    )
    result = ingest_file("LEDGER", "ledger.csv", csv_with_blank_line)
    assert result.rows_inserted == 2
    assert result.row_errors == []


def test_ingest_rejects_ragged_row_missing_trailing_columns(app):
    # a row with fewer fields than the header -- csv.DictReader fills the
    # missing trailing columns with None, which must be a clean rejected
    # row (via _column's None check), not an AttributeError on None.strip()
    ragged_csv = (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
        b"T-2,2025-07-01T09:20:00Z,ETH-USD,BUY\n"
    )
    result = ingest_file("LEDGER", "ledger.csv", ragged_csv)
    assert result.rows_inserted == 1
    assert len(result.row_errors) == 1
    assert "missing column" in result.row_errors[0][1]


def test_ingest_handles_duplicate_reference_within_the_same_file(app):
    # last occurrence wins, and it's reported as a correction (updated),
    # not a second insert
    csv_with_duplicate_ref = (
        b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
        b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,30990.00,SETTLED\n"
    )
    result = ingest_file("LEDGER", "ledger.csv", csv_with_duplicate_ref)
    assert result.rows_inserted == 1
    assert result.rows_updated == 1
    assert SourceRecord.query.filter_by(source_system="LEDGER", external_ref="T-1").count() == 1
    rec = SourceRecord.query.filter_by(source_system="LEDGER", external_ref="T-1").first()
    assert str(rec.amount) == "30990.00000000"
