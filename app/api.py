from flask import Blueprint, jsonify, request

from app.models import ManualMatch, ReconciliationRun, RunResultItem, SourceRecord, UnmatchedAck, db
from app.serializers import serialize_record, serialize_result_item, serialize_run
from app.services.ingest import FileFormatError, ingest_file
from app.services.run_service import run_reconciliation

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.errorhandler(413)
def file_too_large(_exc):
    return jsonify({"error": "File is too large (max 10 MB)."}), 413


@bp.route("/dashboard")
def dashboard():
    runs = ReconciliationRun.query.order_by(ReconciliationRun.run_at.desc()).all()
    return jsonify({
        "runs": [serialize_run(r) for r in runs],
        "ledger_count": SourceRecord.query.filter_by(source_system="LEDGER").count(),
        "statement_count": SourceRecord.query.filter_by(source_system="STATEMENT").count(),
    })


@bp.route("/upload", methods=["POST"])
def upload():
    source_system = request.form.get("source_system")
    file = request.files.get("file")

    if source_system not in ("LEDGER", "STATEMENT"):
        return jsonify({"error": "source_system must be LEDGER or STATEMENT"}), 400
    if not file or not file.filename:
        return jsonify({"error": "no file provided"}), 400

    try:
        result = ingest_file(source_system, file.filename, file.read())
    except FileFormatError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "skipped_duplicate_file": result.skipped_duplicate_file,
        "rows_inserted": result.rows_inserted,
        "rows_updated": result.rows_updated,
        "rows_unchanged": result.rows_unchanged,
        "row_errors": [{"row": n, "message": m} for n, m in result.row_errors],
    })


@bp.route("/runs", methods=["POST"])
def start_run():
    run = run_reconciliation()
    return jsonify(serialize_run(run)), 201


@bp.route("/runs/<int:run_id>")
def run_detail(run_id):
    run = ReconciliationRun.query.get_or_404(run_id)
    items = RunResultItem.query.filter_by(run_id=run_id).all()

    return jsonify({
        "run": serialize_run(run),
        "breaks": [serialize_result_item(i) for i in items if i.bucket == "BREAK"],
        "ok": [serialize_result_item(i) for i in items if i.bucket == "OK"],
        "unmatched_ledger": [serialize_result_item(i) for i in items if i.bucket == "UNMATCHED_LEDGER"],
        "unmatched_statement": [serialize_result_item(i) for i in items if i.bucket == "UNMATCHED_STATEMENT"],
    })


@bp.route("/manual-match", methods=["POST"])
def manual_match():
    data = request.get_json(force=True)
    ledger_record_id = data["ledger_record_id"]
    statement_record_id = data["statement_record_id"]

    exists = ManualMatch.query.filter_by(
        ledger_record_id=ledger_record_id, statement_record_id=statement_record_id
    ).first()
    if not exists:
        db.session.add(ManualMatch(
            ledger_record_id=ledger_record_id,
            statement_record_id=statement_record_id,
            note=data.get("note"),
        ))
        db.session.commit()

    return jsonify({"ok": True})


@bp.route("/unmatched-ack", methods=["POST"])
def unmatched_ack():
    data = request.get_json(force=True)
    source_record_id = data["source_record_id"]

    exists = UnmatchedAck.query.filter_by(source_record_id=source_record_id).first()
    if not exists:
        db.session.add(UnmatchedAck(source_record_id=source_record_id, note=data.get("note")))
        db.session.commit()

    return jsonify({"ok": True})


@bp.route("/records/<record_id>/history")
def record_history(record_id):
    from app.models import SourceRecordHistory
    record = SourceRecord.query.get_or_404(record_id)
    history = (
        SourceRecordHistory.query.filter_by(source_record_id=record.id)
        .order_by(SourceRecordHistory.archived_at.desc())
        .all()
    )
    return jsonify({
        "current": serialize_record(record),
        "history": [
            {
                "executed_at": h.executed_at.isoformat(),
                "instrument": h.instrument,
                "side": h.side,
                "quantity": str(h.quantity),
                "price": str(h.price),
                "amount": str(h.amount),
                "status": h.status,
                "archived_at": h.archived_at.isoformat(),
            }
            for h in history
        ],
    })
