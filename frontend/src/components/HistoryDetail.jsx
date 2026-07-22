import { useEffect, useState } from 'react'
import api from '../api'

function fmtDateTime(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) +
    ', ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

const FIELD_LABELS = {
  project_name: 'Project Name', project_type: 'Project Type', location: 'Location',
  ra_leader: 'RA Leader', approved_by: 'Approved By', reference_no: 'Reference No.',
  company: 'Company', client: 'Client', assessment_date: 'Assessment Date',
}

export default function HistoryDetail({ generationId, onClose }) {
  const [detail, setDetail] = useState(null)
  const [versions, setVersions] = useState([])
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.get(`/history/${generationId}`),
      api.get(`/history/${generationId}/versions`),
    ]).then(([d, v]) => {
      setDetail(d.data)
      setVersions(v.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [generationId])

  async function download(versionNum, doc, fmt) {
    const key = `${versionNum}-${doc}-${fmt}`
    setDownloading(key)
    try {
      const res = await api.get(`/download/${generationId}/version/${versionNum}/${doc}/${fmt}`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `${doc.toUpperCase()}_${detail?.project_details?.project_name || 'report'}_v${versionNum}.${fmt}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Download failed.')
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-start justify-center z-50 overflow-y-auto py-8 px-4" onClick={onClose}>
      <div className="card max-w-3xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">Generation Details</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-2xl leading-none">&times;</button>
        </div>

        {loading && <p className="text-gray-400">Loading…</p>}

        {!loading && detail && (
          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Project Details</h3>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                {Object.entries(FIELD_LABELS).map(([key, label]) => (
                  <div key={key}>
                    <span className="text-gray-500">{label}: </span>
                    <span className="text-gray-900 font-medium">{detail.project_details?.[key] || '—'}</span>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-400 mt-2">Created {fmtDateTime(detail.created_at)}</p>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">
                Feedback History {detail.feedback_history?.length ? `(${detail.feedback_history.length})` : ''}
              </h3>
              {!detail.feedback_history?.length && <p className="text-sm text-gray-400">No feedback given — original version only.</p>}
              {!!detail.feedback_history?.length && (
                <ul className="space-y-2">
                  {detail.feedback_history.map((f, i) => (
                    <li key={i} className="text-sm bg-gray-50 border border-gray-200 rounded-lg p-3">
                      <p className="text-gray-900">{f.feedback}</p>
                      <p className="text-xs text-gray-400 mt-1">{fmtDateTime(f.timestamp)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Versions</h3>
              <ul className="space-y-2">
                {versions.map((v) => (
                  <li key={v.version_num} className="flex flex-wrap items-center gap-3 text-sm bg-gray-50 border border-gray-200 rounded-lg p-3">
                    <div className="flex-1 min-w-0">
                      <span className="font-semibold text-gray-900">Version {v.version_num}</span>
                      {v.is_current && <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Current</span>}
                      <p className="text-gray-600 mt-0.5">{v.feedback ? `Feedback: ${v.feedback}` : 'Original AI-generated draft'}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{fmtDateTime(v.created_at)}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button disabled={downloading === `${v.version_num}-ra-docx`} onClick={() => download(v.version_num, 'ra', 'docx')} className="btn-secondary text-xs py-1">⬇ RA (Word)</button>
                      <button disabled={downloading === `${v.version_num}-ra-pdf`} onClick={() => download(v.version_num, 'ra', 'pdf')} className="btn-secondary text-xs py-1">⬇ RA (PDF)</button>
                      <button disabled={downloading === `${v.version_num}-swp-docx`} onClick={() => download(v.version_num, 'swp', 'docx')} className="btn-green text-xs py-1">⬇ SWP (Word)</button>
                      <button disabled={downloading === `${v.version_num}-swp-pdf`} onClick={() => download(v.version_num, 'swp', 'pdf')} className="btn-green text-xs py-1">⬇ SWP (PDF)</button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
