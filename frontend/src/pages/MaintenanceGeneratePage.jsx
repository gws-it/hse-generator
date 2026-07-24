import { useEffect, useRef, useState } from 'react'
import api from '../api'
import { downloadReportFile } from '../downloadJob'

function todayISO() {
  return new Date().toISOString().slice(0, 10)
}

function firstOfMonthISO() {
  const d = new Date()
  d.setDate(1)
  return d.toISOString().slice(0, 10)
}

export default function MaintenanceGeneratePage() {
  const [projects, setProjects] = useState([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [selectedProject, setSelectedProject] = useState(null)
  const [address, setAddress] = useState('')

  const [showAddForm, setShowAddForm] = useState(false)
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')
  const [addError, setAddError] = useState('')
  const [adding, setAdding] = useState(false)

  const [dateFrom, setDateFrom] = useState(firstOfMonthISO())
  const [dateTo, setDateTo] = useState(todayISO())

  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [photos, setPhotos] = useState([]) // [{file_id, name, date}]
  const [thumbUrls, setThumbUrls] = useState({}) // file_id -> object URL
  const [selectedIds, setSelectedIds] = useState(new Set())

  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState('')
  const [reportId, setReportId] = useState(null)
  const [downloading, setDownloading] = useState(null)
  const [downloadProgress, setDownloadProgress] = useState(null) // {pct, step} while downloading

  // Manual Drive browser -- fallback for photos the auto-search misses (e.g. a
  // typo in the WhatsApp caption sent them to the wrong/_Unsorted folder).
  const [browseOpen, setBrowseOpen] = useState(false)
  const [browseStack, setBrowseStack] = useState([]) // [{id, name}], empty = root
  const [browseFolders, setBrowseFolders] = useState([])
  const [browseImages, setBrowseImages] = useState([])
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState('')
  const [browseThumbUrls, setBrowseThumbUrls] = useState({})
  const [browseSelectedIds, setBrowseSelectedIds] = useState(new Set())

  // Flat "list all photos in this date range, grouped by folder" -- an
  // alternative to clicking through folders one at a time. Groups load fast
  // (just names + counts); thumbnails only load for a group once expanded,
  // since a wide date range can have 100+ folders / 1000+ photos.
  const [flatOpen, setFlatOpen] = useState(false)
  const [flatGroups, setFlatGroups] = useState([]) // [{date, folder_name, photos}]
  const [flatLoading, setFlatLoading] = useState(false)
  const [flatError, setFlatError] = useState('')
  const [expandedDates, setExpandedDates] = useState(new Set()) // date strings
  const [expandedGroups, setExpandedGroups] = useState(new Set()) // "date|folder_name"
  const [flatThumbUrls, setFlatThumbUrls] = useState({})
  const [flatSelectedIds, setFlatSelectedIds] = useState(new Set())

  const thumbUrlsRef = useRef({})
  const browseThumbUrlsRef = useRef({})
  const flatThumbUrlsRef = useRef({})
  const generatingRef = useRef(false)
  const downloadingRef = useRef(false)

  useEffect(() => {
    api.get('/maintenance/projects')
      .then((res) => setProjects(res.data))
      .catch(() => {})
      .finally(() => setProjectsLoading(false))
  }, [])

  useEffect(() => {
    thumbUrlsRef.current = thumbUrls
  }, [thumbUrls])

  useEffect(() => {
    browseThumbUrlsRef.current = browseThumbUrls
  }, [browseThumbUrls])

  useEffect(() => {
    flatThumbUrlsRef.current = flatThumbUrls
  }, [flatThumbUrls])

  useEffect(() => {
    return () => {
      Object.values(thumbUrlsRef.current).forEach((url) => URL.revokeObjectURL(url))
      Object.values(browseThumbUrlsRef.current).forEach((url) => URL.revokeObjectURL(url))
      Object.values(flatThumbUrlsRef.current).forEach((url) => URL.revokeObjectURL(url))
    }
  }, [])

  // Shared by both the folder browser and the flat list -- fetches thumbnails
  // a few at a time instead of all at once (see handleFindPhotos for why).
  async function fetchThumbnailsBatched(items, onBatch) {
    const BATCH_SIZE = 8
    for (let i = 0; i < items.length; i += BATCH_SIZE) {
      const batch = items.slice(i, i + BATCH_SIZE)
      const urls = {}
      await Promise.all(batch.map(async (item) => {
        try {
          const res = await api.get(`/maintenance/photo/${item.file_id}`, { responseType: 'blob' })
          urls[item.file_id] = URL.createObjectURL(res.data)
        } catch {
          // leave missing -- shows a placeholder
        }
      }))
      onBatch(urls)
    }
  }

  const filteredProjects = search.trim()
    ? projects.filter((p) =>
        p.name.toLowerCase().includes(search.toLowerCase()) ||
        p.code.toLowerCase().includes(search.toLowerCase())
      )
    : projects

  // flatGroups (flat [{date, folder_name, photos}]) nested into
  // [{date, folders: [{folder_name, photos}]}] for the date > folder collapse tree.
  const groupedByDate = (() => {
    const byDate = new Map()
    for (const g of flatGroups) {
      if (!byDate.has(g.date)) byDate.set(g.date, [])
      byDate.get(g.date).push(g)
    }
    return [...byDate.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, folders]) => ({ date, folders }))
  })()

  function pickProject(project) {
    setSelectedProject(project)
    setAddress(project.address || '')
    setSearch('')
    setDropdownOpen(false)
    resetSearchResults()
  }

  function resetSearchResults() {
    Object.values(thumbUrlsRef.current).forEach((url) => URL.revokeObjectURL(url))
    setThumbUrls({})
    setPhotos([])
    setSelectedIds(new Set())
    setReportId(null)
    setSearchError('')
    setGenerateError('')
  }

  async function handleAddProject() {
    setAddError('')
    if (!newCode.trim() || !newName.trim()) {
      setAddError('Code and name are required.')
      return
    }
    setAdding(true)
    try {
      const res = await api.post('/maintenance/projects', { code: newCode.trim(), name: newName.trim() })
      const created = { id: res.data.id, code: res.data.code, name: res.data.name, address: '', project_type: 'Green Roof' }
      setProjects((p) => [...p, created])
      pickProject(created)
      setShowAddForm(false)
      setNewCode('')
      setNewName('')
    } catch (err) {
      setAddError(err.response?.data?.detail || 'Could not add project.')
    } finally {
      setAdding(false)
    }
  }

  async function handleFindPhotos() {
    if (!selectedProject) return
    setSearching(true)
    setSearchError('')
    resetSearchResults()
    try {
      const res = await api.get(`/maintenance/projects/${selectedProject.id}/photos`, {
        params: { date_from: dateFrom, date_to: dateTo },
      })
      const found = res.data
      setPhotos(found)
      setSelectedIds(new Set(found.map((p) => p.file_id)))

      // Fetch thumbnails in small batches (not all at once) -- with dozens/hundreds
      // of photos, firing every request simultaneously overwhelms the connection
      // and makes the grid appear to hang instead of loading progressively.
      const THUMB_BATCH_SIZE = 8
      for (let i = 0; i < found.length; i += THUMB_BATCH_SIZE) {
        const batch = found.slice(i, i + THUMB_BATCH_SIZE)
        const batchUrls = {}
        await Promise.all(batch.map(async (photo) => {
          try {
            const imgRes = await api.get(`/maintenance/photo/${photo.file_id}`, { responseType: 'blob' })
            batchUrls[photo.file_id] = URL.createObjectURL(imgRes.data)
          } catch {
            // leave missing -- shows a placeholder
          }
        }))
        setThumbUrls((prev) => ({ ...prev, ...batchUrls }))
      }
    } catch (err) {
      setSearchError(err.response?.data?.detail || 'Could not search Drive for photos.')
    } finally {
      setSearching(false)
    }
  }

  function togglePhoto(fileId) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(fileId)) next.delete(fileId)
      else next.add(fileId)
      return next
    })
  }

  // ── Manual Drive browser (fallback when auto-search misses photos) ────────

  function guessDateForImage(name, stack) {
    const fromName = name.match(/^(\d{4}-\d{2}-\d{2})/)
    if (fromName) return fromName[1]
    const dateCrumb = [...stack].reverse().find((c) => /^\d{4}-\d{2}-\d{2}$/.test(c.name))
    return dateCrumb ? dateCrumb.name : ''
  }

  async function loadBrowseFolder(stack) {
    setBrowseLoading(true)
    setBrowseError('')
    setBrowseSelectedIds(new Set())
    try {
      const folderId = stack.length ? stack[stack.length - 1].id : ''
      const res = await api.get('/maintenance/drive/browse', { params: { folder_id: folderId } })
      setBrowseFolders(res.data.folders || [])
      setBrowseImages(res.data.images || [])
      await fetchThumbnailsBatched(res.data.images || [], (urls) => setBrowseThumbUrls((prev) => ({ ...prev, ...urls })))
    } catch (err) {
      setBrowseError(err.response?.data?.detail || 'Could not browse Drive.')
    } finally {
      setBrowseLoading(false)
    }
  }

  function openBrowser() {
    setFlatOpen(false)
    setBrowseOpen(true)
    setBrowseStack([])
    loadBrowseFolder([])
  }

  function navigateInto(folder) {
    const next = [...browseStack, folder]
    setBrowseStack(next)
    loadBrowseFolder(next)
  }

  function navigateToBreadcrumb(index) {
    // index -1 = root
    const next = index < 0 ? [] : browseStack.slice(0, index + 1)
    setBrowseStack(next)
    loadBrowseFolder(next)
  }

  function toggleBrowseSelect(fileId) {
    setBrowseSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(fileId)) next.delete(fileId)
      else next.add(fileId)
      return next
    })
  }

  function addSelectedFromBrowse() {
    const toAdd = browseImages
      .filter((img) => browseSelectedIds.has(img.file_id))
      .map((img) => ({ file_id: img.file_id, name: img.name, date: guessDateForImage(img.name, browseStack) }))

    setPhotos((prev) => {
      const existingIds = new Set(prev.map((p) => p.file_id))
      return [...prev, ...toAdd.filter((p) => !existingIds.has(p.file_id))]
    })
    setSelectedIds((prev) => new Set([...prev, ...toAdd.map((p) => p.file_id)]))
    setThumbUrls((prev) => {
      const next = { ...prev }
      for (const img of toAdd) {
        if (browseThumbUrls[img.file_id]) next[img.file_id] = browseThumbUrls[img.file_id]
      }
      return next
    })
    setBrowseSelectedIds(new Set())
  }

  // ── Flat "list all photos, grouped by folder" (alternative to browsing) ───

  function groupKey(g) {
    return `${g.date}|${g.folder_name}`
  }

  function toggleDateExpand(date) {
    setExpandedDates((prev) => {
      const next = new Set(prev)
      if (next.has(date)) next.delete(date)
      else next.add(date)
      return next
    })
  }

  async function openFlatList() {
    setBrowseOpen(false)
    setFlatOpen(true)
    setFlatLoading(true)
    setFlatError('')
    setFlatGroups([])
    setExpandedDates(new Set())
    setExpandedGroups(new Set())
    setFlatSelectedIds(new Set())
    try {
      const res = await api.get('/maintenance/drive/browse-flat', { params: { date_from: dateFrom, date_to: dateTo } })
      setFlatGroups(res.data || [])
    } catch (err) {
      setFlatError(err.response?.data?.detail || 'Could not list Drive photos.')
    } finally {
      setFlatLoading(false)
    }
  }

  async function toggleGroupExpand(group) {
    const key = groupKey(group)
    const isOpen = expandedGroups.has(key)
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      if (isOpen) next.delete(key)
      else next.add(key)
      return next
    })
    if (!isOpen) {
      // Load thumbnails lazily, only for the group being expanded.
      const missing = group.photos.filter((p) => !flatThumbUrls[p.file_id])
      if (missing.length) {
        await fetchThumbnailsBatched(missing, (urls) => setFlatThumbUrls((prev) => ({ ...prev, ...urls })))
      }
    }
  }

  function toggleFlatSelect(fileId) {
    setFlatSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(fileId)) next.delete(fileId)
      else next.add(fileId)
      return next
    })
  }

  function selectAllInGroup(group) {
    setFlatSelectedIds((prev) => new Set([...prev, ...group.photos.map((p) => p.file_id)]))
  }

  function clearGroupSelection(group) {
    setFlatSelectedIds((prev) => {
      const next = new Set(prev)
      group.photos.forEach((p) => next.delete(p.file_id))
      return next
    })
  }

  function addSelectedFromFlat() {
    const toAdd = []
    for (const group of flatGroups) {
      for (const photo of group.photos) {
        if (flatSelectedIds.has(photo.file_id)) {
          toAdd.push({ file_id: photo.file_id, name: photo.name, date: group.date })
        }
      }
    }

    setPhotos((prev) => {
      const existingIds = new Set(prev.map((p) => p.file_id))
      return [...prev, ...toAdd.filter((p) => !existingIds.has(p.file_id))]
    })
    setSelectedIds((prev) => new Set([...prev, ...toAdd.map((p) => p.file_id)]))
    setThumbUrls((prev) => {
      const next = { ...prev }
      for (const p of toAdd) {
        if (flatThumbUrls[p.file_id]) next[p.file_id] = flatThumbUrls[p.file_id]
      }
      return next
    })
    setFlatSelectedIds(new Set())
  }

  async function handleGenerate() {
    // Guard with a ref, not just the `generating` state -- state updates are
    // batched/async, so a fast double-click can otherwise start this twice
    // before the button visually disables (this is what caused duplicate
    // MaintenanceReport rows/downloads before).
    if (generatingRef.current) return
    generatingRef.current = true
    setGenerateError('')
    setGenerating(true)
    try {
      const selectedPhotos = photos.filter((p) => selectedIds.has(p.file_id))
      const res = await api.post('/maintenance/generate', {
        project_id: selectedProject.id,
        date_from: dateFrom,
        date_to: dateTo,
        address,
        photos: selectedPhotos,
      })
      setReportId(res.data.report_id)

      // The backend just persisted this address onto the project -- keep the
      // locally-cached project list in sync so it prefills correctly if this
      // project is picked again later in the same session, without a reload.
      if (address) {
        setSelectedProject((p) => (p ? { ...p, address } : p))
        setProjects((prev) => prev.map((p) => (p.id === selectedProject.id ? { ...p, address } : p)))
      }
    } catch (err) {
      setGenerateError(err.response?.data?.detail || 'Generation failed.')
    } finally {
      setGenerating(false)
      generatingRef.current = false
    }
  }

  async function handleDownload(fmt) {
    if (downloadingRef.current) return
    downloadingRef.current = true
    setDownloading(fmt)
    setDownloadProgress({ pct: 0, step: 'Starting…' })
    try {
      const filename = `report_${selectedProject?.name || 'report'}.${fmt}`.replace(/\s+/g, '_')
      await downloadReportFile(reportId, fmt, filename, (pct, step) => setDownloadProgress({ pct, step }))
    } catch {
      alert('Download failed. Please try again.')
    } finally {
      setDownloading(null)
      setDownloadProgress(null)
      downloadingRef.current = false
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Maintenance Report Generator</h1>
        <p className="text-gray-500 text-sm">
          Pick a project, find its photos already uploaded from WhatsApp, and generate the report (checklist + photos in one document).
        </p>
      </div>

      {/* ── Project picker ── */}
      <div className="card">
        <h2 className="text-lg font-bold text-gray-900 mb-3">1. Project</h2>

        {selectedProject ? (
          <div className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded-lg px-4 py-3">
            <div>
              <p className="font-semibold text-gray-900">{selectedProject.code} — {selectedProject.name}</p>
            </div>
            <button className="btn-secondary text-sm" onClick={() => { setSelectedProject(null); resetSearchResults() }}>
              Change
            </button>
          </div>
        ) : (
          <>
            <input
              className="input"
              placeholder={projectsLoading ? 'Loading projects…' : 'Click to browse, or search by name or code…'}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onFocus={() => setDropdownOpen(true)}
              onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
              disabled={projectsLoading}
            />
            {dropdownOpen && (
              <div className="mt-2 max-h-56 overflow-y-auto border border-gray-200 rounded-lg divide-y">
                {filteredProjects.length === 0 && (
                  <p className="p-3 text-sm text-gray-400">No matches.</p>
                )}
                {filteredProjects.slice(0, 30).map((p) => (
                  <button
                    key={p.id}
                    onClick={() => pickProject(p)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50"
                  >
                    <span className="font-medium text-gray-900">{p.code}</span>
                    <span className="text-gray-500"> — {p.name}</span>
                  </button>
                ))}
                {filteredProjects.length > 30 && (
                  <p className="p-2 text-xs text-gray-400 text-center">Showing first 30 — keep typing to narrow it down.</p>
                )}
              </div>
            )}

            <div className="mt-3">
              {!showAddForm ? (
                <button className="text-sm text-blue-700 font-medium" onClick={() => setShowAddForm(true)}>
                  ＋ Add new project
                </button>
              ) : (
                <div className="border border-gray-200 rounded-lg p-3 space-y-2">
                  <input className="input" placeholder="Project code (e.g. AMKSC)" value={newCode} onChange={(e) => setNewCode(e.target.value)} />
                  <input className="input" placeholder="Project name (e.g. Ang Mo Kio Swimming Complex)" value={newName} onChange={(e) => setNewName(e.target.value)} />
                  {addError && <p className="text-sm text-red-600">{addError}</p>}
                  <p className="text-xs text-gray-400">
                    Note: this only adds it here. For future WhatsApp photos to auto-sort into this project, it also needs adding to the bot's project list.
                  </p>
                  <div className="flex gap-2">
                    <button className="btn-primary text-sm" onClick={handleAddProject} disabled={adding}>
                      {adding ? 'Adding…' : 'Add & Select'}
                    </button>
                    <button className="btn-secondary text-sm" onClick={() => setShowAddForm(false)}>Cancel</button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Details + date range ── */}
      {selectedProject && (
        <div className="card">
          <h2 className="text-lg font-bold text-gray-900 mb-3">2. Details & Date Range</h2>
          <label className="label">Client / Site Address (shown on the checklist's "Acknowledged by" field)</label>
          <textarea className="input min-h-[70px] mb-4" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="e.g. ActiveSG Sport Park@Teck Ghee&#10;1771 Ang Mo Kio Ave 1&#10;Singapore 569978" />

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">From</label>
              <input type="date" className="input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div>
              <label className="label">To</label>
              <input type="date" className="input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
          </div>

          <button className="btn-primary mt-4" onClick={handleFindPhotos} disabled={searching}>
            {searching ? 'Searching Drive…' : 'Find Photos'}
          </button>
          {searchError && <p className="text-sm text-red-600 mt-2">{searchError}</p>}

          <div className="mt-4 pt-4 border-t border-gray-100">
            {!browseOpen && !flatOpen ? (
              <div className="flex flex-wrap gap-4">
                <button className="text-sm text-blue-700 font-medium" onClick={openBrowser}>
                  Can't find your photos? Browse Drive folders →
                </button>
                <button className="text-sm text-blue-700 font-medium" onClick={openFlatList}>
                  Or list all photos in this date range →
                </button>
              </div>
            ) : browseOpen ? (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-gray-600">
                    Some photos land in the wrong folder if the WhatsApp caption had a typo — browse for them here instead.
                  </p>
                  <button className="text-xs text-gray-500 font-medium whitespace-nowrap ml-3" onClick={() => setBrowseOpen(false)}>Close</button>
                </div>

                <div className="flex flex-wrap items-center gap-1 text-sm mb-3">
                  <button className="text-blue-700 hover:underline" onClick={() => navigateToBreadcrumb(-1)}>Drive Root</button>
                  {browseStack.map((crumb, i) => (
                    <span key={crumb.id} className="flex items-center gap-1">
                      <span className="text-gray-400">/</span>
                      <button className="text-blue-700 hover:underline" onClick={() => navigateToBreadcrumb(i)}>{crumb.name}</button>
                    </span>
                  ))}
                </div>

                {browseLoading && <p className="text-sm text-gray-400">Loading…</p>}
                {browseError && <p className="text-sm text-red-600">{browseError}</p>}

                {!browseLoading && !browseError && (
                  <>
                    {browseFolders.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-3">
                        {browseFolders.map((folder) => (
                          <button
                            key={folder.id}
                            onClick={() => navigateInto(folder)}
                            className="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50"
                          >
                            📁 {folder.name}
                          </button>
                        ))}
                      </div>
                    )}

                    {browseImages.length > 0 && (
                      <>
                        <div className="flex gap-3 mb-2">
                          <button className="text-xs text-blue-700 font-medium" onClick={() => setBrowseSelectedIds(new Set(browseImages.map((i) => i.file_id)))}>
                            Select all {browseImages.length}
                          </button>
                          <button className="text-xs text-gray-500 font-medium" onClick={() => setBrowseSelectedIds(new Set())}>
                            Clear
                          </button>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 mb-3">
                          {browseImages.map((img) => (
                            <label key={img.file_id} className={`relative border-2 rounded-lg overflow-hidden cursor-pointer ${browseSelectedIds.has(img.file_id) ? 'border-blue-600' : 'border-transparent'}`}>
                              <input
                                type="checkbox"
                                className="absolute top-1.5 left-1.5 w-4 h-4 z-10"
                                checked={browseSelectedIds.has(img.file_id)}
                                onChange={() => toggleBrowseSelect(img.file_id)}
                              />
                              {browseThumbUrls[img.file_id] ? (
                                <img src={browseThumbUrls[img.file_id]} alt={img.name} className="w-full h-28 object-cover" />
                              ) : (
                                <div className="w-full h-28 bg-gray-100 flex items-center justify-center text-xs text-gray-400">Loading…</div>
                              )}
                            </label>
                          ))}
                        </div>
                        <button
                          className="btn-secondary text-sm"
                          onClick={addSelectedFromBrowse}
                          disabled={browseSelectedIds.size === 0}
                        >
                          Add {browseSelectedIds.size} Selected to Report
                        </button>
                      </>
                    )}

                    {browseFolders.length === 0 && browseImages.length === 0 && (
                      <p className="text-sm text-gray-400">This folder is empty.</p>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-gray-600">
                    Every photo folder found between {dateFrom} and {dateTo} — click a group to see its photos.
                  </p>
                  <button className="text-xs text-gray-500 font-medium whitespace-nowrap ml-3" onClick={() => setFlatOpen(false)}>Close</button>
                </div>

                {flatLoading && <p className="text-sm text-gray-400">Scanning Drive — this can take up to 30s for wide date ranges…</p>}
                {flatError && <p className="text-sm text-red-600">{flatError}</p>}

                {!flatLoading && !flatError && flatGroups.length === 0 && (
                  <p className="text-sm text-gray-400">No photos found in this date range.</p>
                )}

                {!flatLoading && !flatError && flatGroups.length > 0 && (
                  <>
                    <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg divide-y mb-3">
                      {groupedByDate.map((dateGroup) => {
                        const dateExpanded = expandedDates.has(dateGroup.date)
                        const totalPhotosForDate = dateGroup.folders.reduce((n, f) => n + f.photos.length, 0)
                        const selectedForDate = dateGroup.folders.reduce(
                          (n, f) => n + f.photos.filter((p) => flatSelectedIds.has(p.file_id)).length, 0
                        )
                        return (
                          <div key={dateGroup.date}>
                            <button
                              onClick={() => toggleDateExpand(dateGroup.date)}
                              className="w-full flex items-center justify-between px-3 py-2.5 text-sm bg-white hover:bg-gray-50 text-left font-semibold"
                            >
                              <span>
                                <span className="text-gray-400 mr-2">{dateExpanded ? '▾' : '▸'}</span>
                                <span className="text-gray-900">{dateGroup.date}</span>
                              </span>
                              <span className="text-xs text-gray-400 font-normal whitespace-nowrap ml-2">
                                {selectedForDate > 0 && <span className="text-blue-600 font-medium">{selectedForDate} selected · </span>}
                                {dateGroup.folders.length} folder{dateGroup.folders.length !== 1 ? 's' : ''} · {totalPhotosForDate} photo{totalPhotosForDate !== 1 ? 's' : ''}
                              </span>
                            </button>

                            {dateExpanded && dateGroup.folders.map((group) => {
                              const key = groupKey(group)
                              const isExpanded = expandedGroups.has(key)
                              const selectedInGroup = group.photos.filter((p) => flatSelectedIds.has(p.file_id)).length
                              return (
                                <div key={key} className="border-t border-gray-100">
                                  <button
                                    onClick={() => toggleGroupExpand(group)}
                                    className="w-full flex items-center justify-between pl-8 pr-3 py-2 text-sm hover:bg-gray-50 text-left"
                                  >
                                    <span>
                                      <span className="text-gray-400 mr-2">{isExpanded ? '▾' : '▸'}</span>
                                      <span className="text-gray-700">{group.folder_name}</span>
                                    </span>
                                    <span className="text-xs text-gray-400 whitespace-nowrap ml-2">
                                      {selectedInGroup > 0 && <span className="text-blue-600 font-medium">{selectedInGroup} selected · </span>}
                                      {group.photos.length} photo{group.photos.length !== 1 ? 's' : ''}
                                    </span>
                                  </button>
                                  {isExpanded && (
                                    <div className="p-3 pl-8 bg-gray-50">
                                      <div className="flex gap-3 mb-2">
                                        <button className="text-xs text-blue-700 font-medium" onClick={() => selectAllInGroup(group)}>
                                          Select all {group.photos.length}
                                        </button>
                                        <button className="text-xs text-gray-500 font-medium" onClick={() => clearGroupSelection(group)}>
                                          Clear
                                        </button>
                                      </div>
                                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                                        {group.photos.map((photo) => (
                                          <label key={photo.file_id} className={`relative border-2 rounded-lg overflow-hidden cursor-pointer ${flatSelectedIds.has(photo.file_id) ? 'border-blue-600' : 'border-transparent'}`}>
                                            <input
                                              type="checkbox"
                                              className="absolute top-1.5 left-1.5 w-4 h-4 z-10"
                                              checked={flatSelectedIds.has(photo.file_id)}
                                              onChange={() => toggleFlatSelect(photo.file_id)}
                                            />
                                            {flatThumbUrls[photo.file_id] ? (
                                              <img src={flatThumbUrls[photo.file_id]} alt={photo.name} className="w-full h-24 object-cover" />
                                            ) : (
                                              <div className="w-full h-24 bg-gray-200 flex items-center justify-center text-xs text-gray-400">Loading…</div>
                                            )}
                                          </label>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        )
                      })}
                    </div>
                    <button
                      className="btn-secondary text-sm"
                      onClick={addSelectedFromFlat}
                      disabled={flatSelectedIds.size === 0}
                    >
                      Add {flatSelectedIds.size} Selected to Report
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Photo picker ── */}
      {photos.length > 0 && (
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-bold text-gray-900">3. Select Photos ({selectedIds.size} of {photos.length})</h2>
            <div className="flex gap-2">
              <button className="text-xs text-blue-700 font-medium" onClick={() => setSelectedIds(new Set(photos.map((p) => p.file_id)))}>Select all</button>
              <button className="text-xs text-gray-500 font-medium" onClick={() => setSelectedIds(new Set())}>Clear</button>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {photos.map((photo) => (
              <label key={photo.file_id} className={`relative border-2 rounded-lg overflow-hidden cursor-pointer ${selectedIds.has(photo.file_id) ? 'border-blue-600' : 'border-transparent'}`}>
                <input
                  type="checkbox"
                  className="absolute top-1.5 left-1.5 w-4 h-4 z-10"
                  checked={selectedIds.has(photo.file_id)}
                  onChange={() => togglePhoto(photo.file_id)}
                />
                {thumbUrls[photo.file_id] ? (
                  <img src={thumbUrls[photo.file_id]} alt={photo.name} className="w-full h-28 object-cover" />
                ) : (
                  <div className="w-full h-28 bg-gray-100 flex items-center justify-center text-xs text-gray-400">Loading…</div>
                )}
                <p className="text-[10px] text-gray-500 text-center py-0.5">{photo.date}</p>
              </label>
            ))}
          </div>

          <button className="btn-green mt-5" onClick={handleGenerate} disabled={generating || selectedIds.size === 0}>
            {generating ? 'Generating…' : `Generate Documents (${selectedIds.size} photos)`}
          </button>
          {generateError && <p className="text-sm text-red-600 mt-2">{generateError}</p>}
        </div>
      )}

      {/* ── Generating ── */}
      {generating && (
        <div className="card flex items-center gap-3">
          <div className="w-5 h-5 border-2 border-green-600 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          <span className="text-sm font-medium text-gray-700">Generating report, please wait…</span>
        </div>
      )}

      {/* ── Download ── */}
      {reportId && !generating && (
        <div className="card">
          <h2 className="text-lg font-bold text-gray-900 mb-3">4. Download</h2>
          <div className="flex flex-wrap gap-2">
            <button className="btn-green text-sm" disabled={downloading === 'docx'} onClick={() => handleDownload('docx')}>⬇ Report (Word)</button>
            <button className="btn-green text-sm" disabled={downloading === 'pdf'} onClick={() => handleDownload('pdf')}>⬇ Report (PDF)</button>
          </div>

          {downloadProgress && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                <span>{downloadProgress.step}</span>
                <span>{downloadProgress.pct}%</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-2">
                <div
                  className="bg-green-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${downloadProgress.pct}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
