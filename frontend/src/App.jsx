import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import GeneratePage from './pages/GeneratePage'
import HistoryPage from './pages/HistoryPage'
import Navbar from './components/Navbar'

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token')
  return token ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route
          path="/generate"
          element={
            <PrivateRoute>
              <Navbar />
              <GeneratePage />
            </PrivateRoute>
          }
        />
        <Route
          path="/history"
          element={
            <PrivateRoute>
              <Navbar />
              <HistoryPage />
            </PrivateRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
