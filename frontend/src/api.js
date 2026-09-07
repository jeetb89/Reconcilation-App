const BASE = '/api'

async function handle(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error || `Request failed: ${res.status}`)
  }
  return res.json()
}

export function getDashboard() {
  return fetch(`${BASE}/dashboard`).then(handle)
}

export function uploadFile(sourceSystem, file) {
  const form = new FormData()
  form.append('source_system', sourceSystem)
  form.append('file', file)
  return fetch(`${BASE}/upload`, { method: 'POST', body: form }).then(handle)
}

export function startRun() {
  return fetch(`${BASE}/runs`, { method: 'POST' }).then(handle)
}

export function getRunDetail(runId) {
  return fetch(`${BASE}/runs/${runId}`).then(handle)
}

export function manualMatch(ledgerRecordId, statementRecordId, note) {
  return fetch(`${BASE}/manual-match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ledger_record_id: ledgerRecordId, statement_record_id: statementRecordId, note }),
  }).then(handle)
}

export function unmatchedAck(sourceRecordId, note) {
  return fetch(`${BASE}/unmatched-ack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_record_id: sourceRecordId, note }),
  }).then(handle)
}

export function getRecordHistory(recordId) {
  return fetch(`${BASE}/records/${recordId}/history`).then(handle)
}
