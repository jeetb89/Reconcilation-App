import { useRef, useState } from 'react'
import { uploadFile } from '../api.js'

export default function UploadForm({ onDone }) {
  const [sourceSystem, setSourceSystem] = useState('LEDGER')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const fileInput = useRef(null)

  async function handleSubmit(e) {
    e.preventDefault()
    const file = fileInput.current.files[0]
    if (!file) return

    setBusy(true)
    setMessage(null)
    try {
      const result = await uploadFile(sourceSystem, file)
      if (result.skipped_duplicate_file) {
        setMessage({ type: 'info', text: `${file.name}: identical file already ingested, skipped.` })
      } else {
        let text = `${file.name}: ${result.rows_inserted} new, ${result.rows_updated} corrected, ${result.rows_unchanged} unchanged.`
        if (result.row_errors.length) text += ` ${result.row_errors.length} row(s) rejected.`
        setMessage({ type: 'info', text })
      }
      fileInput.current.value = ''
      onDone()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <label>
        Source:{' '}
        <select value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)}>
          <option value="LEDGER">Our ledger</option>
          <option value="STATEMENT">Other company's statement</option>
        </select>
      </label>{' '}
      <input type="file" accept=".csv" ref={fileInput} required />{' '}
      <button type="submit" disabled={busy}>{busy ? 'Uploading…' : 'Upload'}</button>
      {message && <div className={`flash ${message.type}`}>{message.text}</div>}
    </form>
  )
}
