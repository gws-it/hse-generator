import { Link } from 'react-router-dom'

const tools = [
  {
    to: '/whse/generate',
    name: 'WHSE Report Generator',
    description: 'Auto-generate Risk Assessment & Safe Work Procedures from a Method Statement.',
  },
  {
    to: '/photobot',
    name: 'Photo to Drive Bot',
    description: 'Status and reconnect controls for the WhatsApp → Google Drive photo bot.',
  },
]

export default function DashboardPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">Tools</h1>
      <p className="text-gray-500 mb-8 text-sm">Pick a tool to get started.</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {tools.map((tool) => (
          <Link
            key={tool.to}
            to={tool.to}
            className="block bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md hover:border-blue-200 transition"
          >
            <h2 className="font-semibold text-gray-900 mb-2">{tool.name}</h2>
            <p className="text-sm text-gray-500">{tool.description}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
