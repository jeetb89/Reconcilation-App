import json

from app.core.reconcile import reconcile
from app.models import ManualMatch, ReconciliationRun, RunResultItem, SourceRecord, UnmatchedAck, db
from app.services.converters import to_canonical


def _serialize_diffs(diffs):
    return json.dumps([
        {
            "field": d.field,
            "ledger_value": str(d.ledger_value),
            "statement_value": str(d.statement_value),
            "delta": str(d.delta) if d.delta is not None else None,
        }
        for d in diffs
    ])


def run_reconciliation() -> ReconciliationRun:
    ledger_rows = SourceRecord.query.filter_by(source_system="LEDGER").all()
    statement_rows = SourceRecord.query.filter_by(source_system="STATEMENT").all()

    id_by_ref = {(r.source_system, r.external_ref): r.id for r in ledger_rows + statement_rows}

    manual_matches = set()
    for mm in ManualMatch.query.all():
        manual_matches.add((mm.ledger_record.external_ref, mm.statement_record.external_ref))

    acknowledged_unmatched = set()
    for ack in UnmatchedAck.query.all():
        rec = ack.source_record
        acknowledged_unmatched.add((rec.source_system, rec.external_ref))

    result = reconcile(
        [to_canonical(r) for r in ledger_rows],
        [to_canonical(r) for r in statement_rows],
        manual_matches=manual_matches,
        acknowledged_unmatched=acknowledged_unmatched,
    )

    ok_count = sum(1 for p in result.matched if p.status == "OK")
    break_count = sum(1 for p in result.matched if p.status == "BREAK")

    run = ReconciliationRun(
        ok_count=ok_count,
        break_count=break_count,
        unmatched_ledger_count=len(result.unmatched_ledger),
        unmatched_statement_count=len(result.unmatched_statement),
    )
    db.session.add(run)
    db.session.flush()

    for pair in result.matched:
        db.session.add(RunResultItem(
            run_id=run.id,
            bucket=pair.status,  # "OK" or "BREAK"
            match_type=pair.match_type,
            ledger_record_id=id_by_ref[("LEDGER", pair.ledger.external_ref)],
            statement_record_id=id_by_ref[("STATEMENT", pair.statement.external_ref)],
            diffs_json=_serialize_diffs(pair.diffs) if pair.diffs else None,
        ))

    for rec in result.unmatched_ledger:
        db.session.add(RunResultItem(
            run_id=run.id,
            bucket="UNMATCHED_LEDGER",
            ledger_record_id=id_by_ref[("LEDGER", rec.external_ref)],
        ))

    for rec in result.unmatched_statement:
        db.session.add(RunResultItem(
            run_id=run.id,
            bucket="UNMATCHED_STATEMENT",
            statement_record_id=id_by_ref[("STATEMENT", rec.external_ref)],
        ))

    db.session.commit()
    return run
