const PROJECT_TYPES = ['Green Wall', 'Green Roof', 'Construction', 'Landscape']

export default function ProjectForm({ values, onChange }) {
  function set(field, value) {
    onChange({ ...values, [field]: value })
  }

  function setMember(idx, value) {
    const members = [...(values.ra_members || ['', '', ''])]
    members[idx] = value
    onChange({ ...values, ra_members: members })
  }

  const members = values.ra_members || ['', '', '']

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="label">Project Name *</label>
          <input className="input" value={values.project_name || ''} onChange={(e) => set('project_name', e.target.value)} placeholder="e.g. IWMF Green Wall Installation" />
        </div>

        <div>
          <label className="label">Project Type *</label>
          <select className="input" value={values.project_type || ''} onChange={(e) => set('project_type', e.target.value)}>
            <option value="">— Select —</option>
            {PROJECT_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>

        <div>
          <label className="label">Reference No.</label>
          <input className="input" value={values.reference_no || ''} onChange={(e) => set('reference_no', e.target.value)} placeholder="e.g. GWS-001-2026" />
        </div>

        <div className="sm:col-span-2">
          <label className="label">Activity Location / Site Address</label>
          <input className="input" value={values.location || ''} onChange={(e) => set('location', e.target.value)} placeholder="e.g. Tuas South – IWMF" />
        </div>

        <div>
          <label className="label">Company</label>
          <input className="input" value={values.company || ''} onChange={(e) => set('company', e.target.value)} placeholder="GWS LIVINGART PTE LTD" />
        </div>

        <div>
          <label className="label">Client</label>
          <input className="input" value={values.client || ''} onChange={(e) => set('client', e.target.value)} />
        </div>

        <div>
          <label className="label">RA Leader / Prepared By</label>
          <input className="input" value={values.ra_leader || ''} onChange={(e) => set('ra_leader', e.target.value)} />
        </div>

        <div>
          <label className="label">Approved By</label>
          <input className="input" value={values.approved_by || ''} onChange={(e) => set('approved_by', e.target.value)} />
        </div>

        <div>
          <label className="label">RA Member 1</label>
          <input className="input" value={members[0] || ''} onChange={(e) => setMember(0, e.target.value)} />
        </div>

        <div>
          <label className="label">RA Member 2</label>
          <input className="input" value={members[1] || ''} onChange={(e) => setMember(1, e.target.value)} />
        </div>

        <div>
          <label className="label">RA Member 3</label>
          <input className="input" value={members[2] || ''} onChange={(e) => setMember(2, e.target.value)} />
        </div>

        <div>
          <label className="label">Assessment Date</label>
          <input className="input" value={values.assessment_date || ''} onChange={(e) => set('assessment_date', e.target.value)} placeholder="16 Jan 2026" />
        </div>
      </div>
    </div>
  )
}
