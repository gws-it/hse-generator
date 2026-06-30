export default function SWPPreview({ swp }) {
  const activities = swp?.activities || []

  if (!activities.length) return <p className="text-gray-400 text-sm">No activities generated.</p>

  return (
    <div>
      {swp.purpose && (
        <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-100">
          <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide mb-1">Purpose</p>
          <p className="text-sm text-gray-700">{swp.purpose}</p>
        </div>
      )}

      <div className="space-y-4">
        {activities.map((act, i) => (
          <div key={i} className="border border-gray-200 rounded-lg overflow-hidden">
            <div className="bg-blue-900 text-white px-4 py-2 text-sm font-semibold">
              {i + 1}. {act.name}
            </div>
            <ol className="list-decimal list-inside px-4 py-3 space-y-1">
              {(act.steps || []).map((step, j) => (
                <li key={j} className="text-sm text-gray-700 py-0.5">{step}</li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  )
}
