import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDashboard, startRun } from '../api.js'
import UploadForm from '../components/UploadForm.jsx'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)

  function refresh() {
    getDashboard().then(setData).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  async function handleStartRun() {
    setStarting(true)
    try {
      await startRun()
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setStarting(false)
    }
  }

  if (error) return <p className="flash error">{error}</p>
  if (!data) return <p>Loading…</p>

  return (
    <div>
      <h1>Reconciliation</h1>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Load files</h2>
        <p>Currently loaded: {data.ledger_count} ledger row(s), {data.statement_count} statement row(s).</p>
        <UploadForm onDone={refresh} />
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Start a run</h2>
        <button onClick={handleStartRun} disabled={starting}>
          {starting ? 'Running…' : 'Start Run'}
        </button>
      </div>

      <h2>Past runs</h2>
      {data.runs.length === 0 ? (
        <p>No runs yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Run</th><th>When</th><th>OK</th><th>Breaks</th>
              <th>Unmatched (ledger)</th><th>Unmatched (statement)</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((run) => (
              <tr key={run.id}>
                <td><Link to={`/runs/${run.id}`}>Run #{run.id}</Link></td>
                <td>{new Date(run.run_at + 'Z').toLocaleString()}</td>
                <td>{run.ok_count}</td>
                <td>{run.break_count}</td>
                <td>{run.unmatched_ledger_count}</td>
                <td>{run.unmatched_statement_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
