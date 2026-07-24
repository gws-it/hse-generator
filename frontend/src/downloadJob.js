import api from './api'

const POLL_INTERVAL_MS = 1000

// Starts the async /download-start + /jobs flow (real progress, instead of a
// blind wait) and triggers the browser download once the file is ready.
// onProgress(percent, step) is called as the backend reports progress.
export async function downloadReportFile(reportId, fmt, filename, onProgress) {
  const start = await api.post(`/maintenance/download-start/${reportId}/${fmt}`)
  const jobId = start.data.job_id

  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/maintenance/jobs/${jobId}`)
        const job = res.data
        onProgress?.(job.progress || 0, job.step || '')

        if (job.status === 'done') {
          clearInterval(interval)
          const fileRes = await api.get(`/maintenance/jobs/${jobId}/file`, { responseType: 'blob' })
          const url = URL.createObjectURL(fileRes.data)
          const a = document.createElement('a')
          a.href = url
          a.download = filename
          a.click()
          URL.revokeObjectURL(url)
          resolve()
        } else if (job.status === 'error') {
          clearInterval(interval)
          reject(new Error(job.error || 'Generation failed'))
        }
      } catch (err) {
        clearInterval(interval)
        reject(err)
      }
    }, POLL_INTERVAL_MS)
  })
}
