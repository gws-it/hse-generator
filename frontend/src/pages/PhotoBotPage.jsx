import { useEffect, useRef, useState } from 'react'
import api from '../api'

const POLL_INTERVAL_MS = 2000
const RECONNECT_TIMEOUT_MS = 90000

export default function PhotoBotPage() {
  const [status, setStatus] = useState(null) // { connected, state, watchedGroups, lastQrAt }
  const [statusError, setStatusError] = useState('')
  const [loading, setLoading] = useState(true)
  const [reconnecting, setReconnecting] = useState(false)
  const [reconnectError, setReconnectError] = useState('')
  const [qrUrl, setQrUrl] = useState(null)

  const pollRef = useRef(null)
  const timeoutRef = useRef(null)
  const qrUrlRef = useRef(null)

  async function fetchStatus() {
    try {
      const res = await api.get('/photobot/status')
      setStatus(res.data)
      setStatusError('')
      return res.data
    } catch (err) {
      setStatusError('Could not reach the Photo to Drive bot. It may be offline.')
      return null
    }
  }

  async function tryFetchQr() {
    try {
      const res = await api.get('/photobot/qr', { responseType: 'blob' })
      const newUrl = URL.createObjectURL(res.data)
      if (qrUrlRef.current) URL.revokeObjectURL(qrUrlRef.current)
      qrUrlRef.current = newUrl
      setQrUrl(newUrl)
    } catch {
      // No fresh QR yet — keep whatever is currently shown (or nothing).
    }
  }

  function stopPolling() {
    if (pollRef.current) clearInterval(pollRef.current)
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    pollRef.current = null
    timeoutRef.current = null
  }

  async function handleReconnect() {
    setReconnectError('')
    setReconnecting(true)
    setQrUrl(null)
    if (qrUrlRef.current) {
      URL.revokeObjectURL(qrUrlRef.current)
      qrUrlRef.current = null
    }

    try {
      await api.post('/photobot/reconnect')
    } catch (err) {
      setReconnectError(err.response?.data?.detail || 'Failed to start reconnect.')
      setReconnecting(false)
      return
    }

    stopPolling()
    pollRef.current = setInterval(async () => {
      const data = await fetchStatus()
      if (data?.connected) {
        setReconnecting(false)
        stopPolling()
        return
      }
      tryFetchQr()
    }, POLL_INTERVAL_MS)

    timeoutRef.current = setTimeout(() => {
      stopPolling()
      setReconnecting(false)
    }, RECONNECT_TIMEOUT_MS)
  }

  useEffect(() => {
    fetchStatus().finally(() => setLoading(false))
    return () => {
      stopPolling()
      if (qrUrlRef.current) URL.revokeObjectURL(qrUrlRef.current)
    }
  }, [])

  const connected = status?.connected === true

  return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">Photo to Drive Bot</h1>
      <p className="text-gray-500 mb-8 text-sm">
        Watches WhatsApp groups and uploads photos to Google Drive automatically.
      </p>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        {loading && <p className="text-sm text-gray-500">Checking status…</p>}

        {!loading && statusError && (
          <p className="text-sm text-red-600">{statusError}</p>
        )}

        {!loading && !statusError && status && (
          <>
            <div className="flex items-center gap-2 mb-4">
              <span className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="font-medium text-gray-900">
                {connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>

            {status.watchedGroups?.length > 0 && (
              <p className="text-sm text-gray-500 mb-4">
                Watching: {status.watchedGroups.join(', ')}
              </p>
            )}

            {!connected && !reconnecting && (
              <div className="border-t border-gray-100 pt-4 mt-4">
                <p className="text-sm text-gray-700 mb-3">
                  Your WhatsApp is disconnected. Press this button and scan the QR code to log in again.
                </p>
                <button
                  onClick={handleReconnect}
                  className="bg-blue-900 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-blue-800 transition"
                >
                  Reconnect
                </button>
                {reconnectError && (
                  <p className="text-sm text-red-600 mt-3">{reconnectError}</p>
                )}
              </div>
            )}

            {reconnecting && (
              <div className="border-t border-gray-100 pt-4 mt-4 text-center">
                <p className="text-sm text-gray-700 mb-3">
                  Open WhatsApp on the bot's phone → Linked Devices → Link a Device, then scan:
                </p>
                {qrUrl ? (
                  <img src={qrUrl} alt="WhatsApp QR code" className="mx-auto w-56 h-56 border border-gray-200 rounded-lg" />
                ) : (
                  <div className="mx-auto w-56 h-56 flex items-center justify-center border border-gray-200 rounded-lg text-sm text-gray-400">
                    Waiting for QR code…
                  </div>
                )}
                <p className="text-xs text-gray-400 mt-3">
                  The code refreshes every ~20-30 seconds — keep this open until it connects.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
