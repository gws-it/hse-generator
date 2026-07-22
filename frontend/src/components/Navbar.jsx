import { Link, useNavigate } from 'react-router-dom'
import { tools } from '../tools'

export default function Navbar({ title = 'GWS Livingart Tools', links = [] }) {
  const navigate = useNavigate()
  const user = JSON.parse(localStorage.getItem('user') || '{}')

  function logout() {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    navigate('/')
  }

  return (
    <nav className="bg-blue-900 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link to="/dashboard" className="font-bold text-lg tracking-tight hover:text-blue-200 transition">
            {title}
          </Link>
          {links.map((link) => (
            <Link key={link.to} to={link.to} className="text-blue-200 hover:text-white text-sm transition">
              {link.label}
            </Link>
          ))}
          <details className="relative">
            <summary className="cursor-pointer list-none text-blue-200 hover:text-white text-sm transition select-none">
              Switch Tool ▾
            </summary>
            <div className="absolute left-0 mt-2 w-56 bg-white rounded-lg shadow-xl py-1 z-50">
              {tools.map((tool) => (
                <Link
                  key={tool.to}
                  to={tool.to}
                  className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  {tool.name}
                </Link>
              ))}
            </div>
          </details>
        </div>
        <div className="flex items-center gap-3">
          {user.picture && (
            <img src={user.picture} alt="avatar" className="w-8 h-8 rounded-full border-2 border-blue-300" />
          )}
          <span className="text-sm text-blue-200">{user.name}</span>
          <button onClick={logout} className="text-xs text-blue-300 hover:text-white transition ml-2">
            Sign out
          </button>
        </div>
      </div>
    </nav>
  )
}
