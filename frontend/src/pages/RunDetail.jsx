import { CheckCircleTwoTone, ExclamationCircleTwoTone } from '@ant-design/icons'
import {
  Button, Card, Col, Popconfirm, Row, Select, Space, Statistic, Table, Tabs, Tag, Typography, message,
} from 'antd'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getRunDetail, manualMatch, unmatchedAck } from '../api.js'

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
  const [data, setData] = useState(null)
  const [matchChoice, setMatchChoice] = useState({})

  function refresh() {
    getRunDetail(runId).then(setData).catch((err) => message.error(err.message))
  }

  useEffect(refresh, [runId])

  async function handleMatch(ledgerRecordId) {
    const statementRecordId = matchChoice[ledgerRecordId]
    if (!statementRecordId) return message.warning('Pick a statement row to match with first.')
    await manualMatch(ledgerRecordId, statementRecordId)
    message.success('Matched. This pairing will hold on future runs.')
    refresh()
  }

  async function handleAck(sourceRecordId) {
    await unmatchedAck(sourceRecordId)
    message.success('Acknowledged as having no pair. Will not resurface on future runs.')
    refresh()
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
        render: (_, rec) => (
          <Space>
            {withMatchSelect && (
              <>
                <Select
                  placeholder="match with…"
                  style={{ width: 220 }}
                  value={matchChoice[rec.id]}
                  onChange={(v) => setMatchChoice((prev) => ({ ...prev, [rec.id]: v }))}
                  options={unmatchedStatement.map((si) => ({
                    value: si.statement_record.id,
                    label: `${si.statement_record.external_ref} (${si.statement_record.instrument}, ${si.statement_record.amount})`,
                  }))}
                />
                <Button size="small" type="primary" onClick={() => handleMatch(rec.id)}>Match</Button>
              </>
            )}
            <Popconfirm title="Mark this row as having no pair?" onConfirm={() => handleAck(rec.id)}>
              <Button size="small">No pair</Button>
            </Popconfirm>
          </Space>
        ),
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
