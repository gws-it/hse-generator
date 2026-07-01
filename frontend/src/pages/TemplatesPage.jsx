import { useEffect, useState } from 'react'
import api from '../api'

const PROJECT_TYPES = ['Green Wall', 'Green Roof', 'Construction', 'Landscape']

export default function TemplatesPage() {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [form, setForm] = useState({ project_type: '', label: '' })
  const [files, setFiles] = useState({ mos: null, ra: null, swp: null })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => { fetchTemplates() }, [])

  async function fetchTemplates() {
    try {
      const res = await api.get('/templates')
      setTemplates(res.data)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(e) {
    e.preventDefault()
    if (!form.project_type || !form.label) { setError('Project type and label are required.'); return }
    if (!files.mos && !files.ra && !files.swp) { setError('Upload at least one file.'); return }

    setError(''); setSuccess(''); setUploading(true)
    const fd = new FormData()
    fd.append('project_type', form.project_type)
    fd.append('label', form.label)
    if (files.mos)  fd.append('mos_file', files.mos)
    if (files.ra)   fd.append('ra_file', files.ra)
    if (files.swp)  fd.append('swp_file', files.swp)

    try {
      await api.post('/templates', fd)
      setSuccess('Template uploaded successfully! AI will use it for future generations.')
      setForm({ project_type: '', label: '' })
      setFiles({ mos: null, ra: null, swp: null })
      fetchTemplates()
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this template?')) return
    await api.delete(`/templates/${id}`)
    fetchTemplates()
  }

  function typeColor(type) {
    const map = { 'Green Wall': 'bg-green-100 text-green-800', 'Green Roof': 'bg-emerald-100 text-emerald-800', Construction: 'bg-orange-100 text-orange-800', Landscape: 'bg-lime-100 text-lime-800' }
    return map[type] || 'bg-gray-100 text-gray-700'
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">Template Library</h1>
      <p className="text-gray-500 text-sm mb-6">
        Upload your existing MOS, RA, and SWP files here. The AI will study them and generate new documents that match your company's style and format.
      </p>

      {/* Upload form */}
      <div className="card mb-8">
        <h2 className="text-base font-bold text-gray-800 mb-4">Upload New Template</h2>
        {error && <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">{error}</div>}
        {success && <div className="mb-3 p-3 bg-green-50 border border-green-200 rounded text-green-700 text-sm">{success}</div>}

        <form onSubmit={handleUpload} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Project Type *</label>
              <select className="input" value={form.project_type} onChange={e => setForm({...form, project_type: e.target.value})}>
                <option value="">— Select —</option>
                {PROJECT_TYPES.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Template Label *</label>
              <input className="input" placeholder="e.g. IWMF Green Wall Example" value={form.label} onChange={e => setForm({...form, label: e.target.value})} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            {[
              { key: 'mos', label: 'MOS File', color: 'blue', desc: 'Method Statement' },
              { key: 'ra',  label: 'RA File',  color: 'orange', desc: 'Risk Assessment' },
              { key: 'swp', label: 'SWP File', color: 'green', desc: 'Safe Work Procedure' },
            ].map(({ key, label, color, desc }) => (
              <div key={key} className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition
                ${files[key] ? `border-${color}-400 bg-${color}-50` : 'border-gray-200 hover:border-gray-400'}`}
                onClick={() => document.getElementById(`file-${key}`).click()}>
                <input id={`file-${key}`} type="file" accept=".pdf,.docx" className="hidden"
                  onChange={e => setFiles({...files, [key]: e.target.files[0]})} />
                <p className="font-semibold text-sm text-gray-700">{label}</p>
                <p className="text-xs text-gray-400">{desc}</p>
                {files[key]
                  ? <p className="text-xs text-green-600 mt-1 truncate">✓ {files[key].name}</p>
                  : <p className="text-xs text-gray-400 mt-1">PDF or DOCX</p>}
              </div>
            ))}
          </div>

          <button type="submit" disabled={uploading} className="btn-primary">
            {uploading ? 'Uploading…' : 'Upload Template'}
          </button>
        </form>
      </div>

      {/* Template list */}
      <h2 className="text-base font-bold text-gray-800 mb-3">Saved Templates ({templates.length})</h2>
      {loading && <p className="text-gray-400 text-sm">Loading…</p>}
      {!loading && templates.length === 0 && (
        <div className="card text-center py-10 text-gray-400 text-sm">
          No templates yet. Upload your first example above.
        </div>
      )}
      <div className="space-y-3">
        {templates.map(t => (
          <div key={t.id} className="card flex items-center gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-gray-800">{t.label}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${typeColor(t.project_type)}`}>{t.project_type}</span>
              </div>
              <div className="flex gap-3 mt-1">
                {t.has_mos && <span className="text-xs text-blue-600">✓ MOS</span>}
                {t.has_ra  && <span className="text-xs text-orange-600">✓ RA</span>}
                {t.has_swp && <span className="text-xs text-green-600">✓ SWP</span>}
                <span className="text-xs text-gray-400">{new Date(t.created_at).toLocaleDateString()}</span>
              </div>
            </div>
            <button onClick={() => handleDelete(t.id)} className="text-red-400 hover:text-red-600 text-sm transition">Delete</button>
          </div>
        ))}
      </div>
    </div>
  )
}
