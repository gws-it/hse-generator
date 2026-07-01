import { useState, useRef, useCallback } from 'react'
import api from '../api'
import ProjectForm from '../components/ProjectForm'
import RAPreview from '../components/RAPreview'
import SWPPreview from '../components/SWPPreview'

const STEPS = ['Upload MOS', 'Project Details', 'Preview & Download']

export default function GeneratePage() {
  const [step, setStep] = useState(0)
  const [mosText, setMosText] = useState('')
  const [projectDetails, setProjectDetails] = useState({})
  const [generationId, setGenerationId] = useState(null)
  const [raSWP, setRaSWP] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [feedbackLoading, setFeedbackLoading] = useState(false)
  const [version, setVersion] = useState(1)
  const [approved, setApproved] = useState(false)
  const [approving, setApproving] = useState(false)
  const [driveUrl, setDriveUrl] = useState('')
  const [uploadMode, setUploadMode] = useState('file') // 'file' | 'drive'
  const [selectedFile, setSelectedFile] = useState(null)
  const fileRef = useRef()

  // ── Step 1: Upload MOS ──────────────────────────────────────────────────

  async function handleUpload() {
    setError('')
    setLoading(true)
    setLoadingMsg('Reading your MOS document…')

    try {
      const formData = new FormData()
      if (uploadMode === 'file') {
        const file = fileRef.current?.files?.[0]
        if (!file) { setError('Please select a file.'); setLoading(false); return }
        formData.append('file', file)
      } else {
        if (!driveUrl.trim()) { setError('Please enter a Google Drive URL.'); setLoading(false); return }
        formData.append('google_drive_url', driveUrl.trim())
      }

      const res = await api.post('/upload-mos', formData)
      const text = res.data.mos_text
      setMosText(text)

      setLoadingMsg('AI is extracting project details…')
      const detailsRes = await api.post('/extract-details', { mos_text: text })
      setProjectDetails({
        ...detailsRes.data,
        assessment_date: detailsRes.data.assessment_date || new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
      })
      setStep(1)
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Please try again.')
    } finally {
      setLoading(false)
      setLoadingMsg('')
    }
  }

  // ── Step 2: Generate with progress ─────────────────────────────────────

  const [progress, setProgress] = useState(0)
  const [progressLabel, setProgressLabel] = useState('')

  async function pollJob(jobId, onDone, onError, startPct, endPct) {
    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const res = await api.get(`/jobs/${jobId}`)
          const job = res.data
          if (job.status === 'done') {
            clearInterval(interval)
            setProgress(endPct)
            onDone(job.result)
            resolve(job.result)
          } else if (job.status === 'error') {
            clearInterval(interval)
            reject(new Error(job.error || 'Generation failed'))
          } else {
            // Still processing — animate progress
            setProgress((p) => Math.min(p + 2, endPct - 5))
          }
        } catch (e) {
          clearInterval(interval)
          reject(e)
        }
      }, 3000)
    })
  }

  async function handleGenerate() {
    setError('')
    setLoading(true)
    setProgress(0)

    try {
      // Step 1: Start RA generation (returns immediately with job_id)
      setProgressLabel('Step 1 of 2 — AI is generating Risk Assessment…')
      setProgress(5)
      const raStart = await api.post('/generate/ra', { mos_text: mosText, project_details: projectDetails })
      const raResult = await pollJob(raStart.data.job_id, () => {}, () => {}, 5, 50)
      setProgress(55)

      // Step 2: Start SWP generation
      setProgressLabel('Step 2 of 2 — AI is generating Safe Work Procedure…')
      setProgress(60)
      const swpStart = await api.post(`/generate/swp/${raResult.generation_id}`)
      const swpResult = await pollJob(swpStart.data.job_id, () => {}, () => {}, 60, 95)
      setProgress(100)

      setGenerationId(raResult.generation_id)
      setRaSWP({ project_type: projectDetails.project_type, ra: raResult.ra, swp: swpResult.swp })
      setStep(2)
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Unknown error'
      setError(`Generation failed: ${detail}`)
    } finally {
      setLoading(false)
      setProgressLabel('')
      setProgress(0)
    }
  }

  // ── Feedback / Regenerate ───────────────────────────────────────────────

  async function handleFeedback() {
    if (!feedback.trim()) return
    setFeedbackLoading(true)
    setError('')
    setProgress(0)
    setProgressLabel('AI is applying your feedback and regenerating…')
    try {
      const start = await api.post('/feedback', { generation_id: generationId, feedback: feedback.trim() })
      setProgress(10)
      const result = await pollJob(start.data.job_id, () => {}, () => {}, 10, 95)
      setProgress(100)
      setRaSWP(result.ra_swp)
      setFeedback('')
      setVersion(v => v + 1)
      setApproved(false)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Feedback failed. Please try again.')
    } finally {
      setFeedbackLoading(false)
      setProgressLabel('')
      setProgress(0)
    }
  }

  async function handleApprove() {
    setApproving(true)
    try {
      await api.post(`/generations/${generationId}/approve`)
      setApproved(true)
    } catch {
      setApproved(true) // still mark as approved even if Drive upload fails
    } finally {
      setApproving(false)
    }
  }

  // ── Download helpers ────────────────────────────────────────────────────

  async function download(doc, fmt, filename) {
    try {
      const res = await api.get(`/download/${generationId}/${doc}/${fmt}`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert('Download failed. Please try again.')
    }
  }

  // ── Drag & drop ─────────────────────────────────────────────────────────

  function handleDrop(e) {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file && fileRef.current) {
      const dt = new DataTransfer()
      dt.items.add(file)
      fileRef.current.files = dt.files
      setSelectedFile(file)
      setUploadMode('file')
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Stepper */}
      <div className="flex items-center mb-8">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
              ${i < step ? 'bg-green-500 text-white' : i === step ? 'bg-blue-700 text-white' : 'bg-gray-200 text-gray-500'}`}>
              {i < step ? '✓' : i + 1}
            </div>
            <span className={`ml-2 text-sm font-medium ${i === step ? 'text-blue-700' : 'text-gray-400'}`}>{s}</span>
            {i < STEPS.length - 1 && <div className="w-12 h-0.5 bg-gray-200 mx-3" />}
          </div>
        ))}
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
      )}

      {(loading || feedbackLoading) && (
        <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin flex-shrink-0" />
            <span className="text-blue-700 text-sm font-medium">{progressLabel || loadingMsg}</span>
          </div>
          {progress > 0 && (
            <div className="w-full bg-blue-100 rounded-full h-2.5 mt-2">
              <div
                className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
          {progress > 0 && (
            <p className="text-xs text-blue-500 mt-1 text-right">{progress}%</p>
          )}
        </div>
      )}

      {/* ── STEP 0: Upload ── */}
      {step === 0 && (
        <div className="card max-w-2xl mx-auto">
          <h2 className="text-xl font-bold text-gray-900 mb-1">Upload Method Statement</h2>
          <p className="text-gray-500 text-sm mb-6">Upload your MOS and the AI will read it to fill in the project details automatically.</p>

          <div className="flex gap-3 mb-5">
            <button
              onClick={() => setUploadMode('file')}
              className={`flex-1 py-2 rounded-lg border text-sm font-medium transition
                ${uploadMode === 'file' ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600'}`}
            >
              Upload from PC
            </button>
            <button
              onClick={() => setUploadMode('drive')}
              className={`flex-1 py-2 rounded-lg border text-sm font-medium transition
                ${uploadMode === 'drive' ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600'}`}
            >
              Google Drive Link
            </button>
          </div>

          {uploadMode === 'file' ? (
            <div
              className={`border-2 border-dashed rounded-xl p-8 text-center transition cursor-pointer
                ${selectedFile ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-blue-400'}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              {selectedFile ? (
                <>
                  <svg className="w-10 h-10 text-green-500 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-green-700 font-medium text-sm">{selectedFile.name}</p>
                  <p className="text-green-500 text-xs mt-1">{(selectedFile.size / 1024).toFixed(0)} KB · Click to change file</p>
                </>
              ) : (
                <>
                  <svg className="w-10 h-10 text-gray-400 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="text-gray-600 text-sm">Drag and drop your MOS here, or <span className="text-blue-600 font-medium">browse</span></p>
                  <p className="text-gray-400 text-xs mt-1">Supports PDF and DOCX files</p>
                </>
              )}
              <input ref={fileRef} type="file" accept=".pdf,.docx" className="hidden"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)} />
            </div>
          ) : (
            <div>
              <label className="label">Google Drive File URL</label>
              <input
                type="url"
                className="input"
                placeholder="https://docs.google.com/document/d/..."
                value={driveUrl}
                onChange={(e) => setDriveUrl(e.target.value)}
              />
              <p className="text-xs text-gray-400 mt-1">Make sure the file is shared as "Anyone with link can view"</p>
            </div>
          )}

          <button onClick={handleUpload} disabled={loading} className="btn-primary w-full mt-6">
            {loading ? 'Processing…' : 'Read MOS →'}
          </button>
        </div>
      )}

      {/* ── STEP 1: Project Form ── */}
      {step === 1 && (
        <div className="card max-w-2xl mx-auto">
          <h2 className="text-xl font-bold text-gray-900 mb-1">Review Project Details</h2>
          <p className="text-gray-500 text-sm mb-6">Details were auto-filled from your MOS. Edit anything that needs correction.</p>
          <ProjectForm values={projectDetails} onChange={setProjectDetails} />
          <div className="flex gap-3 mt-6">
            <button onClick={() => setStep(0)} className="btn-secondary">← Back</button>
            <button onClick={handleGenerate} disabled={loading} className="btn-primary flex-1">
              {loading ? 'Generating…' : 'Generate RA + SWP →'}
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2: Preview & Download ── */}
      {step === 2 && raSWP && (
        <div>
          {/* Download bar */}
          <div className="card mb-6 flex flex-wrap items-center gap-3">
            <div className="flex-1">
              <h2 className="text-lg font-bold text-gray-900">{projectDetails.project_name}</h2>
              <p className="text-sm text-gray-500">{projectDetails.project_type} · {projectDetails.location}</p>
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              {version > 1 && <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded">v{version}</span>}
              <button onClick={() => download('ra', 'docx', `RA_${projectDetails.project_name||'report'}${version>1?`_v${version}`:''}.docx`)} className="btn-secondary text-sm">⬇ RA (Word)</button>
              <button onClick={() => download('ra', 'pdf',  `RA_${projectDetails.project_name||'report'}${version>1?`_v${version}`:''}.pdf`)}  className="btn-secondary text-sm">⬇ RA (PDF)</button>
              <button onClick={() => download('swp','docx', `SWP_${projectDetails.project_name||'report'}${version>1?`_v${version}`:''}.docx`)} className="btn-green text-sm">⬇ SWP (Word)</button>
              <button onClick={() => download('swp','pdf',  `SWP_${projectDetails.project_name||'report'}${version>1?`_v${version}`:''}.pdf`)}  className="btn-green text-sm">⬇ SWP (PDF)</button>
            </div>
          </div>

          {/* RA Preview */}
          <div className="card mb-6">
            <h3 className="text-base font-bold text-gray-800 mb-4">Risk Assessment Preview</h3>
            <RAPreview activities={raSWP.ra?.activities || []} />
          </div>

          {/* SWP Preview */}
          <div className="card mb-6">
            <h3 className="text-base font-bold text-gray-800 mb-4">Safe Work Procedure Preview</h3>
            <SWPPreview swp={raSWP.swp || {}} />
          </div>

          {/* Feedback */}
          {/* Approve */}
          <div className="card mb-6">
            {approved ? (
              <div className="flex items-center gap-3 text-green-700">
                <svg className="w-6 h-6 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <p className="font-semibold">Report approved!</p>
                  <p className="text-sm text-green-600">This report has been saved as a reference for future AI generations.</p>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <p className="font-semibold text-gray-800">Happy with this report?</p>
                  <p className="text-sm text-gray-500">Approving saves it as a reference so the AI generates better reports next time.</p>
                </div>
                <button onClick={handleApprove} disabled={approving} className="btn-green whitespace-nowrap">
                  {approving ? 'Saving…' : 'Approved Report'}
                </button>
              </div>
            )}
          </div>

          {/* Feedback */}
          <div className="card">
            <h3 className="text-base font-bold text-gray-800 mb-2">Something not right? Give feedback</h3>
            <p className="text-sm text-gray-500 mb-3">
              Describe what to fix and the AI will regenerate. Example: "Add chemical hazard for activity 1.6" or "The SWP for planting work is missing soil handling steps."
            </p>
            <textarea
              className="input min-h-[80px] resize-y"
              placeholder="Type your feedback here…"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              disabled={feedbackLoading}
            />
            <div className="flex gap-3 mt-3">
              <button onClick={handleFeedback} disabled={feedbackLoading || !feedback.trim()} className="btn-primary">
                {feedbackLoading ? 'Regenerating…' : 'Fix & Regenerate'}
              </button>
              <button onClick={() => { setStep(0); setRaSWP(null); setMosText(''); setVersion(1); setApproved(false); }} className="btn-secondary">
                Start New
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
