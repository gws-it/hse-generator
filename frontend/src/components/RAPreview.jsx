function rpnClass(rpn) {
  const n = Number(rpn)
  if (n >= 17) return 'bg-red-500 text-white'
  if (n >= 10) return 'bg-orange-400 text-white'
  if (n >= 5) return 'bg-yellow-300 text-gray-800'
  return 'bg-green-400 text-white'
}

function formatControls(c) {
  if (!c) return '—'
  const order = ['elimination', 'substitution', 'engineering', 'administrative', 'ppe']
  return order
    .filter((k) => c[k] && c[k].toUpperCase() !== 'NA')
    .map((k) => `${k.charAt(0).toUpperCase() + k.slice(1)}: ${c[k]}`)
    .join('\n\n')
}

export default function RAPreview({ activities }) {
  if (!activities?.length) return <p className="text-gray-400 text-sm">No activities generated.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse min-w-[1200px]">
        <thead>
          <tr className="bg-blue-900 text-white">
            {['S/N', 'Sub-Activity', 'Hazard / Aspect', 'Possible Injury / Impact',
              'Existing Controls', 'S', 'L', 'RPN',
              'Additional Controls', 'S', 'L', 'RPN',
              'Person', 'Due Date'].map((h) => (
              <th key={h} className="border border-blue-700 px-2 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {activities.map((act, i) => (
            <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-blue-50'}>
              <td className="border border-gray-200 px-2 py-2 font-medium">{act.sn}</td>
              <td className="border border-gray-200 px-2 py-2 font-medium min-w-[150px]">{act.sub_activity}</td>
              <td className="border border-gray-200 px-2 py-2 min-w-[180px]">{act.hazard}</td>
              <td className="border border-gray-200 px-2 py-2 min-w-[150px]">{act.possible_injury}</td>
              <td className="border border-gray-200 px-2 py-2 min-w-[220px] whitespace-pre-line">{formatControls(act.existing_controls)}</td>
              <td className="border border-gray-200 px-2 py-2 text-center">{act.initial_s}</td>
              <td className="border border-gray-200 px-2 py-2 text-center">{act.initial_l}</td>
              <td className={`border border-gray-200 px-2 py-2 text-center font-bold ${rpnClass(act.initial_rpn)}`}>{act.initial_rpn}</td>
              <td className="border border-gray-200 px-2 py-2 min-w-[180px] whitespace-pre-line">{formatControls(act.additional_controls)}</td>
              <td className="border border-gray-200 px-2 py-2 text-center">{act.residual_s}</td>
              <td className="border border-gray-200 px-2 py-2 text-center">{act.residual_l}</td>
              <td className={`border border-gray-200 px-2 py-2 text-center font-bold ${rpnClass(act.residual_rpn)}`}>{act.residual_rpn}</td>
              <td className="border border-gray-200 px-2 py-2">{act.implementation_person}</td>
              <td className="border border-gray-200 px-2 py-2">{act.due_date}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex gap-4 mt-3 text-xs">
        <span className="flex items-center gap-1"><span className="w-4 h-4 rounded bg-green-400 inline-block" /> Low (1–4)</span>
        <span className="flex items-center gap-1"><span className="w-4 h-4 rounded bg-yellow-300 inline-block" /> Medium (5–9)</span>
        <span className="flex items-center gap-1"><span className="w-4 h-4 rounded bg-orange-400 inline-block" /> High (10–16)</span>
        <span className="flex items-center gap-1"><span className="w-4 h-4 rounded bg-red-500 inline-block" /> Critical (17–25)</span>
      </div>
    </div>
  )
}
