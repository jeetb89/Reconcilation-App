from decimal import Decimal

import pytest

from app.core.normalize import normalize_ledger_row, normalize_statement_row, NormalizationError


def test_normalize_ledger_row_basic():
    row = {
        "trade_id": "T-1001", "traded_at": "2025-07-01T09:15:00Z", "instrument": "BTC-USD",
        "side": "BUY", "quantity": "0.50", "price": "62000.00",
        "gross_amount": "31000.00", "state": "SETTLED",
    }
    rec = normalize_ledger_row(row)
    assert rec.source_system == "LEDGER"
    assert rec.external_ref == "T-1001"
    assert rec.side == "BUY"
    assert rec.amount == Decimal("31000.00")
    assert rec.status == "SETTLED"
    assert rec.executed_at.isoformat() == "2025-07-01T09:15:00+00:00"


def test_normalize_statement_row_maps_short_codes():
    row = {
        "reference": "t-1001", "executed_at": "2025-07-01 09:15:00", "symbol": "btc-usd",
        "direction": "B", "qty": "0.5", "unit_price": "62000", "total": "31000.00",
        "status": "SETTLED",
    }
    rec = normalize_statement_row(row)
    assert rec.source_system == "STATEMENT"
    assert rec.external_ref == "T-1001"  # normalized to match ledger casing
    assert rec.instrument == "BTC-USD"
    assert rec.side == "BUY"  # "B" mapped to "BUY"


def test_normalize_rejects_unknown_side():
    row = {
        "reference": "T-2", "executed_at": "2025-07-01 09:15:00", "symbol": "BTC-USD",
        "direction": "X", "qty": "1", "unit_price": "1", "total": "1", "status": "SETTLED",
    }
    with pytest.raises(NormalizationError):
        normalize_statement_row(row)


def test_normalize_rejects_unknown_status():
    row = {
        "trade_id": "T-2", "traded_at": "2025-07-01T09:15:00Z", "instrument": "BTC-USD",
        "side": "BUY", "quantity": "1", "price": "1", "gross_amount": "1", "state": "WEIRD",
    }
    with pytest.raises(NormalizationError):
        normalize_ledger_row(row)
