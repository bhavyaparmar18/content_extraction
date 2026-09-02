import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { SopContentView } from './pages/SopContentView'
import { SopRepository } from './pages/SopRepository'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SopRepository />} />
        <Route path="/sops/:recordId" element={<SopContentView />} />
      </Routes>
    </BrowserRouter>
  )
}
