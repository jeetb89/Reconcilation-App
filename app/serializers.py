import json

from app.models import SourceRecord


def serialize_run(run):
    return {
        "id": run.id,
        "run_at": run.run_at.isoformat(),
        "ok_count": run.ok_count,
        "break_count": run.break_count,
        "unmatched_ledger_count": run.unmatched_ledger_count,
        "unmatched_statement_count": run.unmatched_statement_count,
    }


def serialize_record(record: SourceRecord):
    if record is None:
        return None
    return {
        "id": record.id,
        "source_system": record.source_system,
        "external_ref": record.external_ref,
        "executed_at": record.executed_at.isoformat(),
        "instrument": record.instrument,
        "side": record.side,
        "quantity": str(record.quantity),
        "price": str(record.price),
        "amount": str(record.amount),
        "status": record.status,
    }


def serialize_result_item(item):
    return {
        "id": item.id,
        "bucket": item.bucket,
        "match_type": item.match_type,
        "ledger_record": serialize_record(item.ledger_record),
        "statement_record": serialize_record(item.statement_record),
        "diffs": json.loads(item.diffs_json) if item.diffs_json else [],
    }
