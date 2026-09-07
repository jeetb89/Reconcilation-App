"""File ingestion: raw CSV bytes -> SourceFile + SourceRecord rows.

Handles the two file-arrival rules from the brief:
  - the same file sent twice is a no-op (content hash dedup)
  - a correction file (same source, mostly unchanged rows, a few amounts
    fixed) overwrites SourceRecord in place and archives the old values into
    SourceRecordHistory
"""

import csv
import hashlib
import io
import json
from dataclasses import dataclass

from app.core.normalize import normalize_row, NormalizationError
from app.models import SourceFile, SourceRecord, SourceRecordHistory, db


class FileFormatError(ValueError):
    """Raised for problems with the file as a whole (not a single row) --
    not text, or no header row at all. Distinct from NormalizationError,
    which is always per-row and gets reported as a rejected row instead of
    failing the whole upload."""


@dataclass
class IngestResult:
    skipped_duplicate_file: bool
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    row_errors: list  # list of (row_number, message)


TRACKED_FIELDS = ("executed_at", "instrument", "side", "quantity", "price", "amount", "status")


def _changed(existing: SourceRecord, canonical) -> bool:
    for f in TRACKED_FIELDS:
        old, new = getattr(existing, f), getattr(canonical, f)
        if f == "executed_at":
            # sqlite drops tzinfo on round-trip; both sides are normalized to UTC, so compare naive
            old, new = old.replace(tzinfo=None), new.replace(tzinfo=None)
        if old != new:
            return True
    return False


def ingest_file(source_system: str, filename: str, file_bytes: bytes) -> IngestResult:
    if not file_bytes:
        raise FileFormatError("The file is empty.")

    content_hash = hashlib.sha256(file_bytes).hexdigest()

    if SourceFile.query.filter_by(source_system=source_system, content_hash=content_hash).first():
        return IngestResult(True, 0, 0, 0, [])

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FileFormatError("Could not read this file as text -- is it actually a CSV?")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise FileFormatError("No header row found -- is this a CSV file?")

    # Validate the format up front, before writing anything, so a bad file
    # never leaves a half-created source_file/source_record behind.
    source_file = SourceFile(source_system=source_system, filename=filename, content_hash=content_hash)
    db.session.add(source_file)
    db.session.flush()  # get source_file.id

    inserted = updated = unchanged = 0
    errors = []

    for row_number, row in enumerate(reader, start=2):  # header is line 1
        try:
            canonical = normalize_row(source_system, row)
        except NormalizationError as exc:
            errors.append((row_number, str(exc)))
            continue

        existing = SourceRecord.query.filter_by(
            source_system=source_system, external_ref=canonical.external_ref
        ).first()

        if existing is None:
            db.session.add(SourceRecord(
                source_system=source_system,
                external_ref=canonical.external_ref,
                executed_at=canonical.executed_at,
                instrument=canonical.instrument,
                side=canonical.side,
                quantity=canonical.quantity,
                price=canonical.price,
                amount=canonical.amount,
                status=canonical.status,
                raw_json=json.dumps(canonical.raw),
                source_file_id=source_file.id,
            ))
            inserted += 1
            continue

        if not _changed(existing, canonical):
            unchanged += 1
            continue

        db.session.add(SourceRecordHistory(
            source_record_id=existing.id,
            source_system=existing.source_system,
            external_ref=existing.external_ref,
            executed_at=existing.executed_at,
            instrument=existing.instrument,
            side=existing.side,
            quantity=existing.quantity,
            price=existing.price,
            amount=existing.amount,
            status=existing.status,
            raw_json=existing.raw_json,
            superseded_by_file_id=source_file.id,
        ))

        existing.executed_at = canonical.executed_at
        existing.instrument = canonical.instrument
        existing.side = canonical.side
        existing.quantity = canonical.quantity
        existing.price = canonical.price
        existing.amount = canonical.amount
        existing.status = canonical.status
        existing.raw_json = json.dumps(canonical.raw)
        existing.source_file_id = source_file.id
        updated += 1

    db.session.commit()
    return IngestResult(False, inserted, updated, unchanged, errors)
