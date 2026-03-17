import { useCallback, useEffect, useState } from 'react'
import {
  createUser,
  deleteUser,
  listUsers,
  updateUserRole,
} from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import type { AdminUser } from '@/types/api'

export function AdminDashboard() {
  const { user, session, signOut } = useAuth()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createEmail, setCreateEmail] = useState('')
  const [createPassword, setCreatePassword] = useState('')
  const [createRole, setCreateRole] = useState<'admin' | 'user'>('user')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const token = session?.access_token
  const loadUsers = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const data = await listUsers(token)
      setUsers(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    loadUsers()
  }, [loadUsers])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!token) return
    setCreateError(null)
    setCreating(true)
    try {
      await createUser(token, {
        email: createEmail,
        password: createPassword,
        role: createRole,
      })
      setCreateEmail('')
      setCreatePassword('')
      setCreateRole('user')
      loadUsers()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    if (!token || !confirm('Are you sure you want to delete this user?')) return
    try {
      await deleteUser(token, id)
      loadUsers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete user')
    }
  }

  async function handleRoleChange(id: string, newRole: 'admin' | 'user') {
    if (!token) return
    try {
      await updateUserRole(token, id, newRole)
      loadUsers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update role')
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-900">
            Admin Dashboard
          </h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-slate-600">{user?.email}</span>
            <button
              onClick={() => signOut()}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="p-6 max-w-4xl">
        {/* Create user form */}
        <div className="mb-8 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">
            Create User
          </h2>
          <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-4">
            <div className="flex-1 min-w-[180px]">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Email
              </label>
              <input
                type="email"
                value={createEmail}
                onChange={(e) => setCreateEmail(e.target.value)}
                required
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
              />
            </div>
            <div className="w-40">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Password
              </label>
              <input
                type="password"
                value={createPassword}
                onChange={(e) => setCreatePassword(e.target.value)}
                required
                minLength={6}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
              />
            </div>
            <div className="w-32">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Role
              </label>
              <select
                value={createRole}
                onChange={(e) =>
                  setCreateRole(e.target.value as 'admin' | 'user')
                }
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
              >
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-accent-500 px-4 py-2 font-medium text-white hover:bg-accent-600 disabled:opacity-60"
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
          </form>
          {createError && (
            <p className="mt-2 text-sm text-red-600">{createError}</p>
          )}
        </div>

        {error && (
          <p className="mb-4 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {/* User list */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <h2 className="text-lg font-semibold text-slate-900 px-6 py-4 border-b border-slate-200">
            Users
          </h2>
          {loading ? (
            <div className="px-6 py-12 text-center text-slate-500">
              Loading…
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="px-6 py-3 text-left text-sm font-medium text-slate-700">
                      Email
                    </th>
                    <th className="px-6 py-3 text-left text-sm font-medium text-slate-700">
                      Role
                    </th>
                    <th className="px-6 py-3 text-right text-sm font-medium text-slate-700">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr
                      key={u.id}
                      className="border-b border-slate-100 hover:bg-slate-50"
                    >
                      <td className="px-6 py-3 text-slate-900">
                        {u.email || u.id}
                      </td>
                      <td className="px-6 py-3">
                        <select
                          value={
                            (u.app_metadata?.role as string) || 'user'
                          }
                          onChange={(e) =>
                            handleRoleChange(
                              u.id,
                              e.target.value as 'admin' | 'user'
                            )
                          }
                          className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-900 focus:border-accent-500 focus:outline-none"
                        >
                          <option value="user">user</option>
                          <option value="admin">admin</option>
                        </select>
                      </td>
                      <td className="px-6 py-3 text-right">
                        <button
                          onClick={() => handleDelete(u.id)}
                          className="text-sm text-red-600 hover:text-red-700 font-medium"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!loading && users.length === 0 && (
            <div className="px-6 py-12 text-center text-slate-500">
              No users yet.
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
