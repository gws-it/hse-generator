import { useEffect, useState } from 'react'
import api from '../api'

const TYPE_COLOR = {
  'Green Wall':   'bg-green-100 text-green-800',
  'Green Roof':   'bg-emerald-100 text-emerald-800',
  Construction:   'bg-orange-100 text-orange-800',
  Landscape:      'bg-lime-100 text-lime-800',
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading]     = useState(true)
  const [syncing, setSyncing]     = useState(false)
  const [syncResult, setSyncResult] = useState(null)
  const [error, setError]         = useState('')

  useEffect(() => { fetchTemplates() }, [])

  async function fetchTemplates() {
    try {
      const res = await api.get('/templates')
      setTemplates(res.data)
    } finally {
      setLoading(false)
    }
  }

  async function handleSync() {
    setSyncing(true); setSyncResult(null); setError('')
    try {
      const res = await api.post('/drive-sync')
      setSyncResult(res.data)
      fetchTemplates()
    } catch (err) {
      setError(err.response?.data?.detail || 'Sync failed. Check that GOOGLE_API_KEY or GOOGLE_SERVICE_ACCOUNT_JSON is set in Railway.')
    } finally {
      setSyncing(false)
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this template?')) return
    await api.delete(`/templates/${id}`)
    fetchTemplates()
  }

  const driveTemplates = templates.filter(t => t.label.includes('[Drive]'))
  const autoTemplates  = templates.filter(t => t.label.includes('[Auto]'))
  const userTemplates  = templates.filter(t => !t.label.includes('[Drive]') && !t.label.includes('[Auto]'))

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">Template Library</h1>
      <p className="text-gray-500 text-sm mb-6">
        The AI reads your existing MOS, RA, and SWP documents from Google Drive and uses them as examples when generating new reports.
        Every time your team downloads a generated report, it is automatically saved here so the AI keeps improving.
      </p>

      {/* Drive Sync */}
      <div className="card mb-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="font-bold text-gray-800">Google Drive Sync</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Reads templates from your Drive folder automatically. Add new project-type subfolders and click Sync to update.
            </p>
          </div>
          <button onClick={handleSync} disabled={syncing} className="btn-primary whitespace-nowrap">
            {syncing ? 'Syncing…' : '↻ Sync from Drive'}
          </button>
        </div>

        {error && <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">{error}</div>}

        {syncResult && (
          <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded text-sm text-green-800">
            {syncResult.count > 0
              ? <>Synced {syncResult.count} template{syncResult.count > 1 ? 's' : ''}: {syncResult.synced.map(s => s.project_type).join(', ')}</>
              : 'No matching subfolders found. Make sure your Drive folder has subfolders named: Green Wall, Green Roof, Construction, Landscape.'}
          </div>
        )}

      </div>

      {/* Template sections */}
      {loading && <p className="text-gray-400 text-sm">Loading…</p>}

      {!loading && (
        <>
          <Section title="From Google Drive" items={driveTemplates} onDelete={handleDelete} emptyText="No Drive templates yet — click Sync above." />
          <Section title="Auto-saved (downloaded reports)" items={autoTemplates} onDelete={handleDelete} emptyText="Will appear here after your team downloads generated reports." />
          {userTemplates.length > 0 && <Section title="Manually uploaded" items={userTemplates} onDelete={handleDelete} />}
        </>
      )}
    </div>
  )
}

function Section({ title, items, onDelete, emptyText }) {
  return (
    <div className="mb-6">
      <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wide mb-2">{title} ({items.length})</h2>
      {items.length === 0
        ? <p className="text-gray-400 text-sm italic">{emptyText}</p>
        : (
          <div className="space-y-2">
            {items.map(t => (
              <div key={t.id} className="card flex items-center gap-4 py-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-gray-800 text-sm">{t.label}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLOR[t.project_type] || 'bg-gray-100 text-gray-700'}`}>{t.project_type}</span>
                  </div>
                  <div className="flex gap-3 mt-0.5">
                    {t.has_mos && <span className="text-xs text-blue-500">✓ MOS</span>}
                    {t.has_ra  && <span className="text-xs text-orange-500">✓ RA</span>}
                    {t.has_swp && <span className="text-xs text-green-500">✓ SWP</span>}
                    <span className="text-xs text-gray-400">{new Date(t.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <button onClick={() => onDelete(t.id)} className="text-red-300 hover:text-red-500 text-xs transition">Remove</button>
              </div>
            ))}
          </div>
        )
      }
    </div>
  )
}
