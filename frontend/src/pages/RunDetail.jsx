import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getRunDetail, manualMatch, unmatchedAck } from '../api.js'

function Badge({ className, children }) {
  return <span className={`badge ${className}`}>{children}</span>
}

function RecordRow({ rec, extra }) {
  return (
    <>
      <td>{rec.external_ref}</td>
      <td>{rec.instrument}</td>
      <td>{rec.side}</td>
      <td>{rec.quantity}</td>
      <td>{rec.amount}</td>
      <td>{new Date(rec.executed_at + 'Z').toLocaleString()}</td>
      {extra}
    </>
  )
}

export default function RunDetail() {
  const { runId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [matchChoice, setMatchChoice] = useState({})

  function refresh() {
    getRunDetail(runId).then(setData).catch((err) => setError(err.message))
  }

  useEffect(refresh, [runId])

  async function handleMatch(ledgerRecordId) {
    const statementRecordId = matchChoice[ledgerRecordId]
    if (!statementRecordId) return
    await manualMatch(ledgerRecordId, statementRecordId)
    refresh()
  }

  async function handleAck(sourceRecordId) {
    await unmatchedAck(sourceRecordId)
    refresh()
  }

  if (error) return <p className="flash error">{error}</p>
  if (!data) return <p>Loading…</p>

  const { run, breaks, ok, unmatched_ledger: unmatchedLedger, unmatched_statement: unmatchedStatement } = data

  return (
    <div>
      <h1>Run #{run.id} &mdash; {new Date(run.run_at + 'Z').toLocaleString()}</h1>
      <p>
        <Badge className="ok">{run.ok_count} OK</Badge>{' '}
        <Badge className="break">{run.break_count} breaks</Badge>{' '}
        &middot; {run.unmatched_ledger_count} unmatched ledger
        &middot; {run.unmatched_statement_count} unmatched statement
      </p>

      <h2>Breaks ({breaks.length})</h2>
      {breaks.length === 0 ? <p>None.</p> : (
        <table>
          <thead>
            <tr><th>Ledger ref</th><th>Statement ref</th><th>Match type</th><th>Differing fields</th></tr>
          </thead>
          <tbody>
            {breaks.map((item) => (
              <tr key={item.id}>
                <td>{item.ledger_record.external_ref}</td>
                <td>{item.statement_record.external_ref}</td>
                <td><Badge className={item.match_type.toLowerCase()}>{item.match_type}</Badge></td>
                <td>
                  <table className="nested">
                    <thead><tr><th>field</th><th>ledger</th><th>statement</th><th>delta</th></tr></thead>
                    <tbody>
                      {item.diffs.map((d) => (
                        <tr key={d.field} className="diff-bad">
                          <td>{d.field}</td><td>{d.ledger_value}</td><td>{d.statement_value}</td><td>{d.delta}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Unmatched &mdash; ledger only ({unmatchedLedger.length})</h2>
      {unmatchedLedger.length === 0 ? <p>None.</p> : (
        <table>
          <thead>
            <tr><th>Ref</th><th>Instrument</th><th>Side</th><th>Qty</th><th>Amount</th><th>Executed at</th><th>Resolve</th></tr>
          </thead>
          <tbody>
            {unmatchedLedger.map((item) => {
              const rec = item.ledger_record
              return (
                <tr key={item.id}>
                  <RecordRow
                    rec={rec}
                    extra={
                      <td>
                        <select
                          value={matchChoice[rec.id] || ''}
                          onChange={(e) => setMatchChoice((prev) => ({ ...prev, [rec.id]: e.target.value }))}
                        >
                          <option value="">match with…</option>
                          {unmatchedStatement.map((si) => (
                            <option key={si.statement_record.id} value={si.statement_record.id}>
                              {si.statement_record.external_ref} ({si.statement_record.instrument}, {si.statement_record.amount})
                            </option>
                          ))}
                        </select>{' '}
                        <button onClick={() => handleMatch(rec.id)}>Match</button>{' '}
                        <button onClick={() => handleAck(rec.id)}>No pair</button>
                      </td>
                    }
                  />
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <h2>Unmatched &mdash; statement only ({unmatchedStatement.length})</h2>
      {unmatchedStatement.length === 0 ? <p>None.</p> : (
        <table>
          <thead>
            <tr><th>Ref</th><th>Instrument</th><th>Side</th><th>Qty</th><th>Amount</th><th>Executed at</th><th>Resolve</th></tr>
          </thead>
          <tbody>
            {unmatchedStatement.map((item) => {
              const rec = item.statement_record
              return (
                <tr key={item.id}>
                  <RecordRow
                    rec={rec}
                    extra={<td><button onClick={() => handleAck(rec.id)}>No pair</button></td>}
                  />
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <h2>OK ({ok.length})</h2>
      <details>
        <summary>Show matched, no-issue pairs</summary>
        <table>
          <thead><tr><th>Ledger ref</th><th>Statement ref</th><th>Match type</th></tr></thead>
          <tbody>
            {ok.map((item) => (
              <tr key={item.id}>
                <td>{item.ledger_record.external_ref}</td>
                <td>{item.statement_record.external_ref}</td>
                <td><Badge className={item.match_type.toLowerCase()}>{item.match_type}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}
