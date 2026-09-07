import { Layout, Menu, Typography } from 'antd'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import RunDetail from './pages/RunDetail.jsx'

const { Header, Content } = Layout
const { Title } = Typography

export default function App() {
  const location = useLocation()
  const selectedKey = location.pathname === '/' ? '/' : '/runs'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        <Title level={4} style={{ color: 'white', margin: 0, whiteSpace: 'nowrap' }}>
          Reconciliation
        </Title>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey]}
          items={[{ key: '/', label: <Link to="/">Dashboard</Link> }]}
          style={{ flex: 1, minWidth: 0 }}
        />
      </Header>
      <Content style={{ padding: '24px 48px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/runs/:runId" element={<RunDetail />} />
          </Routes>
        </div>
      </Content>
    </Layout>
  )
}
