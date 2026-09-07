import { InboxOutlined } from '@ant-design/icons'
import { Alert, Select, Space, Upload, message } from 'antd'
import { useState } from 'react'
import { uploadFile } from '../api.js'

const { Dragger } = Upload

export default function UploadForm({ onDone }) {
  const [sourceSystem, setSourceSystem] = useState('LEDGER')
  const [busy, setBusy] = useState(false)

  async function handleUpload({ file, onSuccess, onError }) {
    setBusy(true)
    try {
      const result = await uploadFile(sourceSystem, file)
      if (result.skipped_duplicate_file) {
        message.info(`${file.name}: identical file already ingested, skipped.`)
      } else {
        message.success(
          `${file.name}: ${result.rows_inserted} new, ${result.rows_updated} corrected, ${result.rows_unchanged} unchanged.`,
        )
        if (result.row_errors.length) {
          message.warning(`${result.row_errors.length} row(s) rejected — see details below.`)
        }
      }
      onSuccess(result)
      onDone(result.row_errors || [])
    } catch (err) {
      message.error(err.message)
      onError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Space>
        <span>Source:</span>
        <Select
          value={sourceSystem}
          onChange={setSourceSystem}
          style={{ width: 260 }}
          options={[
            { value: 'LEDGER', label: 'Our ledger' },
            { value: 'STATEMENT', label: "Other company's statement" },
          ]}
        />
      </Space>
      <Dragger
        accept=".csv"
        multiple={false}
        showUploadList={false}
        disabled={busy}
        customRequest={handleUpload}
      >
        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
        <p className="ant-upload-text">Click or drag a CSV file to upload</p>
        <p className="ant-upload-hint">
          Re-uploading an identical file is a no-op. A file with the same rows but a few
          corrected values updates those rows in place.
        </p>
      </Dragger>
    </Space>
  )
}
