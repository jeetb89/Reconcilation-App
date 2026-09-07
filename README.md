# Transaction Reconciliation

The screen someone opens each morning to see where our ledger and the other
company's statement disagree, and to resolve it.

## Stack

Backend: Flask + Flask-SQLAlchemy + SQLite + pytest, exposing a JSON API
under `/api/*`. Frontend: React (Vite) + Ant Design, a single-page app that
talks to that API — `frontend/src/pages/Dashboard.jsx` and `RunDetail.jsx`
are the two screens (drag-and-drop upload, sortable/expandable tables,
tabs for breaks/unmatched/OK, toast notifications for every action).

## Running it

One command, both services:
```
./run_dev.sh
```
Creates the venv and installs both dependency sets on first run, then starts
Flask (http://127.0.0.1:5000) and the Vite dev server
(http://localhost:5173) together. Open http://localhost:5173. Ctrl+C stops
both.

`./run_dev.sh prod` instead builds the frontend once and runs Flask alone,
serving the built assets at http://127.0.0.1:5000 — one process, one port,
no Vite server needed.

Or run each side by hand, in two terminals:
```
# terminal 1
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py          # http://127.0.0.1:5000

# terminal 2
cd frontend
npm install
npm run dev             # http://localhost:5173, proxies /api to :5000
```

Upload the sample files from `sample_data/` in this order to see every case
in one pass:

1. `ledger_2025-07-01.csv` (source: "Our ledger")
2. `statement_2025-07-01.csv` (source: "Other company's statement")
3. Start a run.
4. Try re-uploading `ledger_2025-07-01.csv` again — it's a no-op (same file).
5. Upload `ledger_2025-07-01_correction.csv` — same file, one row's amount
   fixed (T-1009). Start a run again and watch that row move from BREAK to OK.
6. On the run screen, manually match `T-1008` (unmatched ledger) with
   `C-9002` (unmatched statement) — same trade, different reference schemes.
   Also try "No pair" on `T-1007`. Start another run: both decisions hold.

## Tests

```
python -m pytest
```

20 tests. `tests/test_normalize.py` and `tests/test_reconcile.py` cover the
matching/comparison core with **no database and no Flask app** — plain
dataclasses in, dataclasses out. `tests/test_ingest_and_run.py` covers file
idempotency, corrections, and manual-match/ack persistence against a real
(temp) SQLite database.

## Design

### The six tables

| Table | Purpose |
|---|---|
| `source_file` | Where did this data come from? (dedup by content hash) |
| `source_record` | What does the source currently say, per `(source_system, external_ref)`? |
| `source_record_history` | What did it say before a correction overwrote it? |
| `reconciliation_run` | When did we reconcile, and what were the totals? |
| `run_result_item` | What did we conclude for each record/pair, that run? |
| `manual_match` / `unmatched_ack` | Human decisions — a forced pairing, or "this genuinely has no pair" — that must hold on every future run. |

### The core logic is pure

`app/core/normalize.py` and `app/core/reconcile.py` take and return plain
dataclasses (`CanonicalRecord`, `MatchedPair`, `ReconciliationResult`). They
import nothing from Flask or SQLAlchemy. The DB and HTTP layers
(`app/services/`, `app/api.py`) are thin — they load rows, call these
functions, and persist the result. This is what the brief asks for
("testable without a database and without a browser"), and it's what let me
write `test_reconcile.py` as thirteen tiny in-memory cases instead of
database fixtures. The React frontend is thinner still — it only calls
`app/api.py` and renders what comes back; none of the reconciliation logic
lives in the browser.

### Matching

Auto-match is a join on normalized `external_ref` (case/whitespace
normalized, since one source could plausibly send `t-1001` and the other
`T-1001`). Cancelled trades are filtered out **before** matching — they're
never compared, per the brief. Manual matches are applied next (for cases
where the two sides never shared an identifier scheme, e.g. `T-1008` vs
`C-9002`), then whatever's left, minus acknowledged-unmatched rows, is
reported as genuinely unmatched.

### Comparison tolerances (decided, documented here since the brief left this open)

- **Amount**: OK if within **$1.00 absolute** *or* **0.1% relative** to the
  larger of the two amounts (whichever is more forgiving — a flat tolerance
  dominates on small trades, a percentage on large ones). Rounding and small
  fees pass; a mispriced trade (e.g. a $170 gap on a $34k trade, ~0.5%) does
  not.
- **Time**: OK if within **30 minutes**. This is generous on purpose — the
  brief's own example shows a 40-minute gap on an otherwise-clean trade, and
  clock skew between two independently-operated systems can plausibly be
  that large. Anything past that is treated as a real discrepancy worth a
  human's attention, not clock drift.
- **Instrument / side / quantity / status**: compared for exact equality.
  These define the identity of the trade rather than its economics — any
  mismatch is a break regardless of size, since it likely means the "match"
  itself is wrong, not just imprecise.

Both values are stored as `Decimal`, not `float`, throughout — the DB
columns are `Numeric`, and comparisons never touch floating point.

### Corrections and history

Uniqueness is on `(source_system, external_ref)` in `source_record`. On
ingest, if a row with that key already exists and any tracked field differs,
the *old* values are archived into `source_record_history` before being
overwritten. If the incoming values are identical to what's already stored,
nothing happens — this is what makes re-sending the exact same file (or a
correction file where most rows are unchanged) safe to replay.

File-level idempotency is a second, cheaper check: `source_file` is unique
on `(source_system, content_hash)`, so a byte-for-byte duplicate upload is
rejected before any row parsing happens at all.

### Manual resolution persists

`manual_match` and `unmatched_ack` are looked up fresh at the start of every
`run_reconciliation()` call and applied before the auto-matcher decides
what's unmatched. A human's decision from yesterday is never re-asked.

### Runs are incremental, not a full rescan every time

The first run reconciles everything. Every run after that only re-examines:
- records inserted or corrected since the last run (`source_record.updated_at
  > last_run.run_at`),
- the entire unmatched pool from the last run (a new counterpart might exist
  now for any of them),
- anything currently referenced by a `manual_match` or `unmatched_ack`
  (so those decisions get re-verified, not just trusted forever), and
- the existing counterpart of anything in the above, since `reconcile()`
  needs both sides of a pair together to compare them.

Everything else — a matched pair from last run where neither side changed —
is copied forward into the new run's `run_result_item` rows as-is, never
re-fed through the matcher. On a sample run with 45 loaded records and 17
already-matched pairs, a no-op second run touches only the 9-record
unmatched pool instead of all 45, and produces a byte-for-byte identical
result.

This lives entirely in `app/services/run_service.py` — `app/core/reconcile.py`
stays a pure function over whatever list it's handed, unaware that its
input might be a subset. Correctness for this is tested with a *differential*
test (`tests/test_incremental_matches_full_rescan.py`) that, at every step
of a multi-day scenario, independently runs a from-scratch full rescan and
asserts the incremental result matches it exactly — "faster" is worthless
if it's not identical, so that's the property actually under test.

## What I left out

- **Auth / multi-user attribution.** `matched_by` / `acknowledged_by` fields
  aren't there — there's no user model. In a real system these actions
  would carry an operator identity.
- **Undo for manual matches/acks.** Once made, a decision can't be reversed
  from the UI. Would add a "reverse" action + an audit row rather than a
  hard delete.
- **Multi-period runs.** Everything is one flat pool of "current"
  `source_record`s; there's no explicit trading-day/period boundary. A
  production version would scope runs to a date range so a correction to
  last Tuesday's file doesn't get compared against today's incoming rows.
- **Fuzzy matching.** Only exact `external_ref` matching is automatic;
  anything without a shared reference relies on a human. A same-side
  candidate search (by instrument + amount + time proximity) to *suggest*
  likely manual matches would remove most of that manual work.
- **Pagination / large files.** Sample data is a handful of rows; the run
  screen renders everything inline with no paging.
- **Frontend tests.** All test coverage is on the Python side (the logic
  that matters, per the brief). The React components are thin rendering of
  API responses with no independent logic, so I didn't add a JS test
  runner for this scope.

## What I'd do next

- Suggested-match ranking for the unmatched screen (score candidates by
  amount/time proximity instead of a flat dropdown of every unmatched row).
- A "what changed since last run" diff view, so a recurring break that's
  already been triaged doesn't need re-reading every morning.
- Config-driven tolerances (currently constants in `app/core/reconcile.py`)
  so ops can tune them without a code change.
