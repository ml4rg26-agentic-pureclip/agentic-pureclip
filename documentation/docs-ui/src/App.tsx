import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import BiologyPage from './pages/BiologyPage'
import DataPage from './pages/DataPage'
import LogicPage from './pages/LogicPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/biology" replace />} />
        <Route path="/biology" element={<BiologyPage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/logic" element={<LogicPage />} />
      </Route>
    </Routes>
  )
}
