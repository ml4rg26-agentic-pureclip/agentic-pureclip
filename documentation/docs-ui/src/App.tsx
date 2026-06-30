import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import BiologyPage from './pages/BiologyPage'
import BioConceptsPage from './pages/BioConceptsPage'
import DataPage from './pages/DataPage'
import LogicPage from './pages/LogicPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/bio-terms" replace />} />
        <Route path="/bio-terms" element={<BiologyPage />} />
        <Route path="/bio-concepts" element={<BioConceptsPage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/logic" element={<LogicPage />} />
      </Route>
    </Routes>
  )
}
