import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import GeneratePage from './pages/GeneratePage'
import HistoryPage from './pages/HistoryPage'
import TemplatesPage from './pages/TemplatesPage'
import PhotoBotPage from './pages/PhotoBotPage'
import Navbar from './components/Navbar'

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token')
  return token ? children : <Navigate to="/" replace />
}

const whseNavLinks = [
  { to: '/whse/generate', label: 'Generate' },
  { to: '/whse/history', label: 'History' },
  { to: '/whse/templates', label: 'Templates' },
]

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route
          path="/dashboard"
          element={
            <PrivateRoute>
              <Navbar title="GWS Livingart Tools" links={[]} />
              <DashboardPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/whse/generate"
          element={
            <PrivateRoute>
              <Navbar title="WHSE Report Generator" links={whseNavLinks} />
              <GeneratePage />
            </PrivateRoute>
          }
        />
        <Route
          path="/whse/history"
          element={
            <PrivateRoute>
              <Navbar title="WHSE Report Generator" links={whseNavLinks} />
              <HistoryPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/whse/templates"
          element={
            <PrivateRoute>
              <Navbar title="WHSE Report Generator" links={whseNavLinks} />
              <TemplatesPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/photobot"
          element={
            <PrivateRoute>
              <Navbar title="Photo to Drive Bot" links={[]} />
              <PhotoBotPage />
            </PrivateRoute>
          }
        />

        {/* Legacy bookmarks from before the /whse prefix existed */}
        <Route path="/generate" element={<Navigate to="/whse/generate" replace />} />
        <Route path="/history" element={<Navigate to="/whse/history" replace />} />
        <Route path="/templates" element={<Navigate to="/whse/templates" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
