import json

from app.core.records import CanonicalRecord
from app.models import SourceRecord


def to_canonical(row: SourceRecord) -> CanonicalRecord:
    return CanonicalRecord(
        source_system=row.source_system,
        external_ref=row.external_ref,
        executed_at=row.executed_at,
        instrument=row.instrument,
        side=row.side,
        quantity=row.quantity,
        price=row.price,
        amount=row.amount,
        status=row.status,
        raw=json.loads(row.raw_json),
    )
