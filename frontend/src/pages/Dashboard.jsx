import { PlayCircleOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, Row, Space, Statistic, Table, Tag, Typography, message } from 'antd'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDashboard, startRun } from '../api.js'
import UploadForm from '../components/UploadForm.jsx'

const { Title } = Typography

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [starting, setStarting] = useState(false)
  const [rowErrors, setRowErrors] = useState([])

  function refresh() {
    getDashboard()
      .then(setData)
      .catch((err) => message.error(err.message))
  }

  useEffect(refresh, [])

  async function handleStartRun() {
    if (starting) return // guard against a rapid double-click firing two runs
    setStarting(true)
    try {
      const run = await startRun()
      message.success(`Run #${run.id} complete.`)
      refresh()
    } catch (err) {
      message.error(err.message)
    } finally {
      setStarting(false)
    }
  }

  function handleUploadDone(errors) {
    setRowErrors(errors)
    refresh()
  }

  if (!data) return null

  const runColumns = [
    {
      title: 'Run',
      dataIndex: 'id',
      render: (id) => <Link to={`/runs/${id}`}>Run #{id}</Link>,
    },
    {
      title: 'When',
      dataIndex: 'run_at',
      render: (v) => new Date(v + 'Z').toLocaleString(),
    },
    { title: 'OK', dataIndex: 'ok_count', render: (v) => <Tag color="green">{v}</Tag> },
    { title: 'Breaks', dataIndex: 'break_count', render: (v) => <Tag color={v > 0 ? 'red' : 'default'}>{v}</Tag> },
    { title: 'Unmatched (ledger)', dataIndex: 'unmatched_ledger_count' },
    { title: 'Unmatched (statement)', dataIndex: 'unmatched_statement_count' },
  ]

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Title level={2} style={{ margin: 0 }}>Reconciliation</Title>

      <Row gutter={16}>
        <Col span={12}>
          <Card>
            <Row gutter={16}>
              <Col span={12}><Statistic title="Ledger rows loaded" value={data.ledger_count} /></Col>
              <Col span={12}><Statistic title="Statement rows loaded" value={data.statement_count} /></Col>
            </Row>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="Start a run">
            <Button type="primary" icon={<PlayCircleOutlined />} loading={starting} onClick={handleStartRun}>
              {starting ? 'Running…' : 'Start Run'}
            </Button>
            <p style={{ marginTop: 12, marginBottom: 0 }}>
              Reconciles everything currently loaded and snapshots the result.
            </p>
          </Card>
        </Col>
      </Row>

      <Card title="Load files">
        <UploadForm onDone={handleUploadDone} />
        {rowErrors.length > 0 && (
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message={`${rowErrors.length} row(s) rejected during normalization`}
            description={
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {rowErrors.map((e, i) => <li key={i}>row {e.row}: {e.message}</li>)}
              </ul>
            }
          />
        )}
      </Card>

      <Card title="Past runs">
        <Table
          rowKey="id"
          columns={runColumns}
          dataSource={data.runs}
          pagination={false}
          locale={{ emptyText: 'No runs yet.' }}
        />
      </Card>
    </Space>
  )
}
