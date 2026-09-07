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


def _load_manual_matches():
    matches = set()
    for mm in ManualMatch.query.all():
        matches.add((mm.ledger_record.external_ref, mm.statement_record.external_ref))
    return matches


def _load_acknowledged_unmatched():
    acks = set()
    for ack in UnmatchedAck.query.all():
        rec = ack.source_record
        acks.add((rec.source_system, rec.external_ref))
    return acks


def _records_by_id(ids):
    if not ids:
        return []
    return SourceRecord.query.filter(SourceRecord.id.in_(ids)).all()


def _pick_working_set(last_run):
    """Decide which records actually need to go through reconcile() again,
    versus which matched pairs can be trusted to still hold from the last
    run's snapshot untouched.

    A record must be re-examined if:
      - it's new or was corrected since the last run (updated_at moved), or
      - it was unmatched last run (a new counterpart might now exist for
        it -- this pool has to be re-checked on every run regardless of
        whether anything in it changed), or
      - it's currently acknowledged as having no pair (same reasoning: a
        genuine counterpart could still arrive later and should win), or
      - it's the counterpart of another record that needs re-examining
        (its own comparison result depends on that record's current value).

    Everything else -- a matched pair from last run where neither side has
    changed -- is carried forward as-is.
    """
    dirty_ledger_ids = {
        r.id for r in SourceRecord.query.filter(
            SourceRecord.source_system == "LEDGER", SourceRecord.updated_at > last_run.run_at
        )
    }
    dirty_statement_ids = {
        r.id for r in SourceRecord.query.filter(
            SourceRecord.source_system == "STATEMENT", SourceRecord.updated_at > last_run.run_at
        )
    }

    recompute_ledger_ids = set(dirty_ledger_ids)
    recompute_statement_ids = set(dirty_statement_ids)

    for ack in UnmatchedAck.query.all():
        rec = ack.source_record
        (recompute_ledger_ids if rec.source_system == "LEDGER" else recompute_statement_ids).add(rec.id)

    for mm in ManualMatch.query.all():
        recompute_ledger_ids.add(mm.ledger_record_id)
        recompute_statement_ids.add(mm.statement_record_id)

    last_items = RunResultItem.query.filter_by(run_id=last_run.id).all()

    # Pass 1: an unmatched row from last run always goes back into the pool
    # (a new counterpart might exist now), which can still grow the
    # recompute sets beyond dirty/ack/manual-match.
    ok_break_items = []
    for item in last_items:
        if item.bucket == "UNMATCHED_LEDGER":
            recompute_ledger_ids.add(item.ledger_record_id)
        elif item.bucket == "UNMATCHED_STATEMENT":
            recompute_statement_ids.add(item.statement_record_id)
        else:  # OK or BREAK
            ok_break_items.append(item)

    # Pass 2: if either side of an already-matched pair is dirty, its
    # counterpart has to come along too -- reconcile() needs both sides
    # together to re-compare them, not just the one side that changed.
    for item in ok_break_items:
        if item.ledger_record_id in dirty_ledger_ids or item.statement_record_id in dirty_statement_ids:
            recompute_ledger_ids.add(item.ledger_record_id)
            recompute_statement_ids.add(item.statement_record_id)

    # Pass 3: now that the working set is final, a matched pair is only
    # carried forward if NEITHER side ended up in it for any reason above --
    # otherwise it would be both carried forward *and* recomputed fresh,
    # duplicating it in this run's output.
    carried_forward = [
        item for item in ok_break_items
        if item.ledger_record_id not in recompute_ledger_ids
        and item.statement_record_id not in recompute_statement_ids
    ]

    return recompute_ledger_ids, recompute_statement_ids, carried_forward


def run_reconciliation() -> ReconciliationRun:
    last_run = ReconciliationRun.query.order_by(ReconciliationRun.run_at.desc()).first()

    if last_run is None:
        ledger_rows = SourceRecord.query.filter_by(source_system="LEDGER").all()
        statement_rows = SourceRecord.query.filter_by(source_system="STATEMENT").all()
        carried_forward = []
    else:
        recompute_ledger_ids, recompute_statement_ids, carried_forward = _pick_working_set(last_run)
        ledger_rows = _records_by_id(recompute_ledger_ids)
        statement_rows = _records_by_id(recompute_statement_ids)

    id_by_ref = {(r.source_system, r.external_ref): r.id for r in ledger_rows + statement_rows}

    result = reconcile(
        [to_canonical(r) for r in ledger_rows],
        [to_canonical(r) for r in statement_rows],
        manual_matches=_load_manual_matches(),
        acknowledged_unmatched=_load_acknowledged_unmatched(),
    )

    fresh_ok = sum(1 for p in result.matched if p.status == "OK")
    fresh_break = sum(1 for p in result.matched if p.status == "BREAK")
    carried_ok = sum(1 for i in carried_forward if i.bucket == "OK")
    carried_break = sum(1 for i in carried_forward if i.bucket == "BREAK")

    run = ReconciliationRun(
        ok_count=fresh_ok + carried_ok,
        break_count=fresh_break + carried_break,
        unmatched_ledger_count=len(result.unmatched_ledger),
        unmatched_statement_count=len(result.unmatched_statement),
    )
    db.session.add(run)
    db.session.flush()

    for item in carried_forward:
        db.session.add(RunResultItem(
            run_id=run.id,
            bucket=item.bucket,
            match_type=item.match_type,
            ledger_record_id=item.ledger_record_id,
            statement_record_id=item.statement_record_id,
            diffs_json=item.diffs_json,
        ))

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
