import { useCallback, useEffect, useState } from 'react'
import { Outlet, useNavigate, useParams } from 'react-router-dom'
import { createCodebase, listCodebases } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import type { Codebase } from '@/types/api'

export function UserDashboard() {
  const { user, session, signOut } = useAuth()
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()
  const [codebases, setCodebases] = useState<Codebase[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createDesc, setCreateDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const token = session?.access_token

  const loadCodebases = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const data = await listCodebases(token)
      setCodebases(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load codebases')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    loadCodebases()
  }, [loadCodebases])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!token) return
    setCreateError(null)
    setCreating(true)
    try {
      const cb = await createCodebase(token, {
        name: createName,
        description: createDesc || undefined,
      })
      setCreateName('')
      setCreateDesc('')
      setShowCreate(false)
      loadCodebases()
      navigate(`/dashboard/codebases/${cb.id}`)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Side pane */}
      <aside className="w-64 border-r border-slate-200 bg-white flex flex-col shrink-0">
        <header className="border-b border-slate-200 px-4 py-3">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-semibold text-slate-900">
              CodeGraph
            </h1>
            <button
              onClick={() => signOut()}
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Logout
            </button>
          </div>
          <p className="text-xs text-slate-500 mt-1 truncate">{user?.email}</p>
        </header>

        <div className="p-3 border-b border-slate-200">
          <h2 className="text-sm font-medium text-slate-700 mb-2">
            My Codebases
          </h2>
          <button
            onClick={() => setShowCreate(true)}
            className="w-full rounded-lg bg-accent-500 px-3 py-2 text-sm font-medium text-white hover:bg-accent-600"
          >
            New Codebase
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="py-4 text-center text-sm text-slate-500">
              Loading…
            </div>
          ) : (
            <ul className="space-y-0.5">
              {codebases.map((cb) => (
                <li key={cb.id}>
                  <button
                    onClick={() => navigate(`/dashboard/codebases/${cb.id}`)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm font-medium truncate ${
                      id === cb.id
                        ? 'bg-accent-500/10 text-accent-600'
                        : 'text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    {cb.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!loading && codebases.length === 0 && !showCreate && (
            <p className="py-4 text-sm text-slate-500 text-center">
              No codebases yet
            </p>
          )}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        {showCreate && (
          <div className="m-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm max-w-md">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">
              New Codebase
            </h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  required
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Description (optional)
                </label>
                <input
                  type="text"
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
                />
              </div>
              {createError && (
                <p className="text-sm text-red-600">{createError}</p>
              )}
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-lg bg-accent-500 px-4 py-2 font-medium text-white hover:bg-accent-600 disabled:opacity-60"
                >
                  {creating ? 'Creating…' : 'Create'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowCreate(false)
                    setCreateError(null)
                  }}
                  className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {error && (
          <div className="m-6 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {!showCreate && (
          <div className="p-6">
            {id ? (
              <Outlet />
            ) : (
              <div className="flex items-center justify-center min-h-[40vh] text-slate-500">
                Select a codebase from the side pane or create a new one.
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
