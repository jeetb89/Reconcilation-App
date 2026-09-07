from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class SourceFile(db.Model):
    """Where did this data come from? One row per uploaded file."""
    __tablename__ = "source_file"

    id = db.Column(db.Integer, primary_key=True)
    source_system = db.Column(db.String(32), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    content_hash = db.Column(db.String(64), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("source_system", "content_hash", name="uq_source_file_hash"),
    )


class SourceRecord(db.Model):
    """What does the source currently say about this trade? One row per
    (source_system, external_ref) -- overwritten in place as corrections arrive."""
    __tablename__ = "source_record"

    id = db.Column(db.Integer, primary_key=True)
    source_system = db.Column(db.String(32), nullable=False)
    external_ref = db.Column(db.String(64), nullable=False)
    executed_at = db.Column(db.DateTime(timezone=True), nullable=False)
    instrument = db.Column(db.String(32), nullable=False)
    side = db.Column(db.String(8), nullable=False)
    quantity = db.Column(db.Numeric(20, 8), nullable=False)
    price = db.Column(db.Numeric(20, 8), nullable=False)
    amount = db.Column(db.Numeric(20, 8), nullable=False)
    status = db.Column(db.String(16), nullable=False)
    raw_json = db.Column(db.Text, nullable=False)
    source_file_id = db.Column(db.Integer, db.ForeignKey("source_file.id"), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    source_file = db.relationship("SourceFile")

    __table_args__ = (
        db.UniqueConstraint("source_system", "external_ref", name="uq_source_record_ref"),
    )


class SourceRecordHistory(db.Model):
    """What did it say before? Append-only snapshot written whenever a
    correction changes an existing SourceRecord."""
    __tablename__ = "source_record_history"

    id = db.Column(db.Integer, primary_key=True)
    source_record_id = db.Column(db.Integer, db.ForeignKey("source_record.id"), nullable=False)
    source_system = db.Column(db.String(32), nullable=False)
    external_ref = db.Column(db.String(64), nullable=False)
    executed_at = db.Column(db.DateTime(timezone=True), nullable=False)
    instrument = db.Column(db.String(32), nullable=False)
    side = db.Column(db.String(8), nullable=False)
    quantity = db.Column(db.Numeric(20, 8), nullable=False)
    price = db.Column(db.Numeric(20, 8), nullable=False)
    amount = db.Column(db.Numeric(20, 8), nullable=False)
    status = db.Column(db.String(16), nullable=False)
    raw_json = db.Column(db.Text, nullable=False)
    superseded_by_file_id = db.Column(db.Integer, db.ForeignKey("source_file.id"), nullable=False)
    archived_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class ReconciliationRun(db.Model):
    """When did we reconcile? One row per run of the matcher."""
    __tablename__ = "reconciliation_run"

    id = db.Column(db.Integer, primary_key=True)
    run_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    ok_count = db.Column(db.Integer, default=0, nullable=False)
    break_count = db.Column(db.Integer, default=0, nullable=False)
    unmatched_ledger_count = db.Column(db.Integer, default=0, nullable=False)
    unmatched_statement_count = db.Column(db.Integer, default=0, nullable=False)


class RunResultItem(db.Model):
    """What did we conclude during that run? One row per bucketed record/pair."""
    __tablename__ = "run_result_item"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("reconciliation_run.id"), nullable=False)
    bucket = db.Column(db.String(16), nullable=False)  # "OK" / "BREAK" / "UNMATCHED_LEDGER" / "UNMATCHED_STATEMENT"
    match_type = db.Column(db.String(8), nullable=True)  # "AUTO" / "MANUAL", only for matched pairs
    ledger_record_id = db.Column(db.Integer, db.ForeignKey("source_record.id"), nullable=True)
    statement_record_id = db.Column(db.Integer, db.ForeignKey("source_record.id"), nullable=True)
    diffs_json = db.Column(db.Text, nullable=True)  # serialized FieldDiff list, only for BREAK

    run = db.relationship("ReconciliationRun")
    ledger_record = db.relationship("SourceRecord", foreign_keys=[ledger_record_id])
    statement_record = db.relationship("SourceRecord", foreign_keys=[statement_record_id])


class ManualMatch(db.Model):
    """Human says these two are the same."""
    __tablename__ = "manual_match"

    id = db.Column(db.Integer, primary_key=True)
    ledger_record_id = db.Column(db.Integer, db.ForeignKey("source_record.id"), nullable=False)
    statement_record_id = db.Column(db.Integer, db.ForeignKey("source_record.id"), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    matched_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    ledger_record = db.relationship("SourceRecord", foreign_keys=[ledger_record_id])
    statement_record = db.relationship("SourceRecord", foreign_keys=[statement_record_id])

    __table_args__ = (
        db.UniqueConstraint("ledger_record_id", "statement_record_id", name="uq_manual_match_pair"),
    )


class UnmatchedAck(db.Model):
    """Human says this genuinely has no pair."""
    __tablename__ = "unmatched_ack"

    id = db.Column(db.Integer, primary_key=True)
    source_record_id = db.Column(db.Integer, db.ForeignKey("source_record.id"), nullable=False, unique=True)
    note = db.Column(db.String(255), nullable=True)
    acknowledged_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    source_record = db.relationship("SourceRecord")
