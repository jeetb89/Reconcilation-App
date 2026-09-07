"""Concurrent/repeated-action edge cases: two requests racing the same
check-then-insert path (double click, two browser tabs, a retried request)
must not 500 on the DB's unique constraint.
"""

from concurrent.futures import ThreadPoolExecutor

from app.models import ManualMatch, UnmatchedAck
from app.services.ingest import ingest_file

LEDGER_CSV = (
    b"trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
    b"T-1,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000.00,SETTLED\n"
)
STATEMENT_CSV = (
    b"reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
    b"C-9,2025-07-01 09:50:00,ETH-USD,B,2,3400,6800.00,SETTLED\n"
)


def test_concurrent_manual_match_requests_dont_500(app, client):
    with app.app_context():
        ingest_file("LEDGER", "ledger.csv", LEDGER_CSV)
        ingest_file("STATEMENT", "statement.csv", STATEMENT_CSV)
        from app.models import SourceRecord
        ledger_id = SourceRecord.query.filter_by(source_system="LEDGER", external_ref="T-1").first().id
        statement_id = SourceRecord.query.filter_by(source_system="STATEMENT", external_ref="C-9").first().id

    def post():
        with app.app_context():
            return client.post(
                "/api/manual-match",
                json={"ledger_record_id": ledger_id, "statement_record_id": statement_id},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(), range(2)))

    for resp in responses:
        assert resp.status_code == 200, resp.get_json()

    with app.app_context():
        assert ManualMatch.query.count() == 1  # never duplicated despite the race


def test_concurrent_unmatched_ack_requests_dont_500(app, client):
    with app.app_context():
        ingest_file("LEDGER", "ledger.csv", LEDGER_CSV)
        from app.models import SourceRecord
        record_id = SourceRecord.query.filter_by(source_system="LEDGER", external_ref="T-1").first().id

    def post():
        with app.app_context():
            return client.post("/api/unmatched-ack", json={"source_record_id": record_id})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(), range(2)))

    for resp in responses:
        assert resp.status_code == 200, resp.get_json()

    with app.app_context():
        assert UnmatchedAck.query.count() == 1


def test_manual_match_missing_fields_is_a_clean_400(client):
    resp = client.post("/api/manual-match", json={})
    assert resp.status_code == 400


def test_manual_match_nonexistent_record_is_a_clean_404(client):
    resp = client.post(
        "/api/manual-match", json={"ledger_record_id": 999999, "statement_record_id": 999999}
    )
    assert resp.status_code == 404
