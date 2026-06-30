import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

export default function LoginPage() {
  const navigate = useNavigate()

  useEffect(() => {
    if (localStorage.getItem('token')) {
      navigate('/generate')
      return
    }

    window.handleGoogleLogin = async (response) => {
      try {
        const res = await api.post('/auth/google', { credential: response.credential })
        localStorage.setItem('token', res.data.token)
        localStorage.setItem('user', JSON.stringify(res.data.user))
        navigate('/generate')
      } catch (err) {
        alert('Login failed. Please try again.')
      }
    }
  }, [navigate])

  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-900 to-blue-700">
      <div className="bg-white rounded-2xl shadow-2xl p-10 w-full max-w-md text-center">
        <div className="mb-6">
          <div className="w-16 h-16 bg-blue-900 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">HSE Report Generator</h1>
          <p className="text-gray-500 mt-2 text-sm">
            Auto-generate Risk Assessment &amp; Safe Work Procedures from your Method Statement
          </p>
        </div>

        <div className="border-t border-gray-100 pt-6">
          <p className="text-sm text-gray-600 mb-4">Sign in with your company Google account</p>
          {clientId ? (
            <div
              id="g_id_onload"
              data-client_id={clientId}
              data-callback="handleGoogleLogin"
              data-auto_prompt="false"
            />
          ) : null}
          <div
            className="g_id_signin flex justify-center"
            data-type="standard"
            data-shape="rectangular"
            data-theme="outline"
            data-text="sign_in_with"
            data-size="large"
            data-logo_alignment="left"
            data-client_id={clientId}
            data-callback="handleGoogleLogin"
          />
          {!clientId && (
            <p className="text-red-500 text-xs mt-3">
              VITE_GOOGLE_CLIENT_ID not configured. See setup instructions.
            </p>
          )}
        </div>

        <p className="mt-6 text-xs text-gray-400">
          GWS Livingart Pte Ltd · Internal Tool
        </p>
      </div>
    </div>
  )
}
