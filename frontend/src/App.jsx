import { Link, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import RunDetail from './pages/RunDetail.jsx'

export default function App() {
  return (
    <div className="app">
      <nav>
        <Link to="/">Dashboard</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/runs/:runId" element={<RunDetail />} />
      </Routes>
    </div>
  )
}
