import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

export default function HistoryPage() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/history').then((r) => { setHistory(r.data); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  function typeColor(type) {
    const map = { 'Green Wall': 'bg-green-100 text-green-800', 'Green Roof': 'bg-emerald-100 text-emerald-800', Construction: 'bg-orange-100 text-orange-800', Landscape: 'bg-lime-100 text-lime-800' }
    return map[type] || 'bg-gray-100 text-gray-700'
  }

  function download(id, doc, fmt) {
    const a = document.createElement('a')
    a.href = `/api/download/${id}/${doc}/${fmt}`
    a.click()
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Generation History</h1>
        <button onClick={() => navigate('/generate')} className="btn-primary text-sm">+ New Report</button>
      </div>

      {loading && <p className="text-gray-400">Loading…</p>}

      {!loading && history.length === 0 && (
        <div className="card text-center py-12">
          <p className="text-gray-400 text-sm">No reports generated yet.</p>
          <button onClick={() => navigate('/generate')} className="btn-primary mt-4">Generate your first report</button>
        </div>
      )}

      <div className="space-y-3">
        {history.map((gen) => (
          <div key={gen.id} className="card flex flex-wrap items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-semibold text-gray-900 truncate">{gen.project_name || 'Untitled'}</h3>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${typeColor(gen.project_type)}`}>{gen.project_type}</span>
                {gen.feedback_count > 0 && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">{gen.feedback_count} feedback{gen.feedback_count > 1 ? 's' : ''}</span>
                )}
              </div>
              <p className="text-sm text-gray-500 mt-0.5">{gen.location} · {new Date(gen.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => download(gen.id, 'ra', 'docx')} className="btn-secondary text-xs py-1">⬇ RA (Word)</button>
              <button onClick={() => download(gen.id, 'ra', 'pdf')} className="btn-secondary text-xs py-1">⬇ RA (PDF)</button>
              <button onClick={() => download(gen.id, 'swp', 'docx')} className="btn-green text-xs py-1">⬇ SWP (Word)</button>
              <button onClick={() => download(gen.id, 'swp', 'pdf')} className="btn-green text-xs py-1">⬇ SWP (PDF)</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
