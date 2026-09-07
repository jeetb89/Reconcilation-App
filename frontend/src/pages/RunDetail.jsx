import { CheckCircleTwoTone, ExclamationCircleTwoTone } from '@ant-design/icons'
import {
  Button, Card, Col, Popconfirm, Row, Select, Space, Statistic, Table, Tabs, Tag, Typography, message,
} from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getRunDetail, manualMatch, startRun, unmatchedAck } from '../api.js'

const { Title } = Typography

function matchTypeTag(matchType) {
  return <Tag color={matchType === 'MANUAL' ? 'blue' : 'default'}>{matchType}</Tag>
}

function fmtTime(v) {
  return new Date(v + 'Z').toLocaleString()
}

const diffColumns = [
  { title: 'Field', dataIndex: 'field' },
  { title: 'Ledger', dataIndex: 'ledger_value' },
  { title: 'Statement', dataIndex: 'statement_value' },
  { title: 'Delta', dataIndex: 'delta' },
]

export default function RunDetail() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [matchChoice, setMatchChoice] = useState({})
  // Tracks rows with a resolve action in flight, so a rapid double-click on
  // the same row can't fire the request twice before it's resolved.
  const [busyIds, setBusyIds] = useState(() => new Set())

  function refresh() {
    getRunDetail(runId).then(setData).catch((err) => message.error(err.message))
  }

  useEffect(refresh, [runId])

  function clearBusy(id) {
    setBusyIds((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }

  // A manual-match/ack decision is saved immediately, but it only changes
  // what a run *concludes* the next time reconciliation actually runs --
  // this run's own result rows are a fixed snapshot from when it executed
  // and never change. So after saving the decision, trigger a fresh run and
  // jump to it; re-fetching this same run would just show the identical,
  // now-stale snapshot and look like the click did nothing.
  async function runAgainAndShowIt() {
    const newRun = await startRun()
    navigate(`/runs/${newRun.id}`)
    if (String(newRun.id) === String(runId)) refresh() // already there -- refetch instead of no-op navigate
  }

  async function handleMatch(ledgerRecordId) {
    if (busyIds.has(ledgerRecordId)) return
    const statementRecordId = matchChoice[ledgerRecordId]
    if (!statementRecordId) return message.warning('Pick a statement row to match with first.')

    setBusyIds((prev) => new Set(prev).add(ledgerRecordId))
    try {
      await manualMatch(ledgerRecordId, statementRecordId)
      message.success('Matched -- running reconciliation again to show it.')
      await runAgainAndShowIt()
    } catch (err) {
      message.error(err.message)
    } finally {
      clearBusy(ledgerRecordId)
    }
  }

  async function handleAck(sourceRecordId) {
    if (busyIds.has(sourceRecordId)) return

    setBusyIds((prev) => new Set(prev).add(sourceRecordId))
    try {
      await unmatchedAck(sourceRecordId)
      message.success('Acknowledged -- running reconciliation again to show it.')
      await runAgainAndShowIt()
    } catch (err) {
      message.error(err.message)
    } finally {
      clearBusy(sourceRecordId)
    }
  }

  if (!data) return null

  const { run, breaks, ok, unmatched_ledger: unmatchedLedger, unmatched_statement: unmatchedStatement } = data

  const pairColumns = [
    { title: 'Ledger ref', dataIndex: ['ledger_record', 'external_ref'] },
    { title: 'Statement ref', dataIndex: ['statement_record', 'external_ref'] },
    { title: 'Match type', dataIndex: 'match_type', render: matchTypeTag },
  ]

  const breakColumns = [
    ...pairColumns,
    { title: 'Fields differing', render: (_, item) => item.diffs.map((d) => d.field).join(', ') },
  ]

  function unmatchedColumns(withMatchSelect) {
    const cols = [
      { title: 'Ref', dataIndex: 'external_ref' },
      { title: 'Instrument', dataIndex: 'instrument' },
      { title: 'Side', dataIndex: 'side', render: (v) => <Tag>{v}</Tag> },
      { title: 'Qty', dataIndex: 'quantity' },
      { title: 'Amount', dataIndex: 'amount' },
      { title: 'Executed at', dataIndex: 'executed_at', render: fmtTime },
      {
        title: 'Resolve',
        render: (_, rec) => {
          const busy = busyIds.has(rec.id)
          return (
            <Space>
              {withMatchSelect && (
                <>
                  <Select
                    placeholder="match with…"
                    style={{ width: 220 }}
                    value={matchChoice[rec.id]}
                    disabled={busy}
                    onChange={(v) => setMatchChoice((prev) => ({ ...prev, [rec.id]: v }))}
                    options={unmatchedStatement.map((si) => ({
                      value: si.statement_record.id,
                      label: `${si.statement_record.external_ref} (${si.statement_record.instrument}, ${si.statement_record.amount})`,
                    }))}
                  />
                  <Button size="small" type="primary" loading={busy} onClick={() => handleMatch(rec.id)}>
                    Match
                  </Button>
                </>
              )}
              <Popconfirm title="Mark this row as having no pair?" onConfirm={() => handleAck(rec.id)}>
                <Button size="small" loading={busy}>No pair</Button>
              </Popconfirm>
            </Space>
          )
        },
      },
    ]
    return cols
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Title level={2} style={{ margin: 0 }}>
        Run #{run.id} <Typography.Text type="secondary" style={{ fontSize: 16 }}>{fmtTime(run.run_at)}</Typography.Text>
      </Title>

      <Card>
        <Row gutter={32}>
          <Col><Statistic title="OK" value={run.ok_count} prefix={<CheckCircleTwoTone twoToneColor="#52c41a" />} /></Col>
          <Col><Statistic title="Breaks" value={run.break_count} prefix={<ExclamationCircleTwoTone twoToneColor="#f5222d" />} /></Col>
          <Col><Statistic title="Unmatched (ledger)" value={run.unmatched_ledger_count} /></Col>
          <Col><Statistic title="Unmatched (statement)" value={run.unmatched_statement_count} /></Col>
        </Row>
      </Card>

      <Tabs
        defaultActiveKey="breaks"
        items={[
          {
            key: 'breaks',
            label: `Breaks (${breaks.length})`,
            children: (
              <Table
                rowKey="id"
                columns={breakColumns}
                dataSource={breaks}
                pagination={false}
                expandable={{
                  expandedRowRender: (item) => (
                    <Table rowKey="field" columns={diffColumns} dataSource={item.diffs} pagination={false} size="small" />
                  ),
                }}
                locale={{ emptyText: 'None.' }}
              />
            ),
          },
          {
            key: 'unmatched-ledger',
            label: `Unmatched — ledger (${unmatchedLedger.length})`,
            children: (
              <Table
                rowKey="id"
                columns={unmatchedColumns(true)}
                dataSource={unmatchedLedger.map((i) => i.ledger_record)}
                pagination={false}
                locale={{ emptyText: 'None.' }}
              />
            ),
          },
          {
            key: 'unmatched-statement',
            label: `Unmatched — statement (${unmatchedStatement.length})`,
            children: (
              <Table
                rowKey="id"
                columns={unmatchedColumns(false)}
                dataSource={unmatchedStatement.map((i) => i.statement_record)}
                pagination={false}
                locale={{ emptyText: 'None.' }}
              />
            ),
          },
          {
            key: 'ok',
            label: `OK (${ok.length})`,
            children: (
              <Table rowKey="id" columns={pairColumns} dataSource={ok} pagination={false} locale={{ emptyText: 'None.' }} />
            ),
          },
        ]}
      />
    </Space>
  )
}
