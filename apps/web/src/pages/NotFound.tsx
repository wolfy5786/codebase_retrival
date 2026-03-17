import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="text-center">
        <h1 className="text-4xl font-semibold text-slate-900 mb-2">404</h1>
        <p className="text-slate-600 mb-6">Page not found</p>
        <Link
          to="/"
          className="text-accent-500 hover:text-accent-600 font-medium"
        >
          Back to login
        </Link>
      </div>
    </div>
  )
}
