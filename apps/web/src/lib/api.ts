import type {
  AdminUser,
  Codebase,
  CodebaseDetail,
  CodebaseListResponse,
  IngestionJobResponse,
  UserMe,
} from '@/types/api'

const API_BASE = import.meta.env.VITE_API_URL || ''

async function apiFetch<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> {
  const { token, ...init } = options
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || err.message || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// Auth
export async function getMe(token: string): Promise<UserMe> {
  return apiFetch<UserMe>('/api/v1/auth/me', { token })
}

// Admin
export async function listUsers(token: string): Promise<AdminUser[]> {
  const data = await apiFetch<{ users?: AdminUser[] } | AdminUser[]>(
    '/api/v1/admin/users',
    { token }
  )
  if (Array.isArray(data)) return data
  return (data as { users: AdminUser[] }).users ?? []
}

export async function createUser(
  token: string,
  body: { email: string; password: string; role: 'admin' | 'user' }
): Promise<AdminUser> {
  return apiFetch<AdminUser>('/api/v1/admin/users', {
    method: 'POST',
    body: JSON.stringify(body),
    token,
  })
}

export async function deleteUser(token: string, id: string): Promise<void> {
  return apiFetch(`/api/v1/admin/users/${id}`, { method: 'DELETE', token })
}

export async function updateUserRole(
  token: string,
  id: string,
  role: 'admin' | 'user'
): Promise<void> {
  return apiFetch(`/api/v1/admin/users/${id}/role`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
    token,
  })
}

// Codebases
export async function listCodebases(token: string): Promise<Codebase[]> {
  const data = await apiFetch<CodebaseListResponse>('/api/v1/codebases', {
    token,
  })
  return data.codebases ?? []
}

export async function getCodebase(
  token: string,
  id: string
): Promise<CodebaseDetail> {
  return apiFetch<CodebaseDetail>(`/api/v1/codebases/${id}`, { token })
}

export async function createCodebase(
  token: string,
  body: { name: string; description?: string }
): Promise<Codebase> {
  return apiFetch<Codebase>('/api/v1/codebases', {
    method: 'POST',
    body: JSON.stringify(body),
    token,
  })
}

export async function deleteCodebase(token: string, id: string): Promise<void> {
  return apiFetch(`/api/v1/codebases/${id}`, { method: 'DELETE', token })
}

// Ingestion
export async function ingestCodebase(
  token: string,
  codebaseId: string,
  file: File
): Promise<IngestionJobResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  }
  const res = await fetch(
    `${API_BASE}/api/v1/codebases/${codebaseId}/ingest`,
    {
      method: 'POST',
      headers,
      body: formData,
    }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || err.message || `HTTP ${res.status}`)
  }
  return res.json() as Promise<IngestionJobResponse>
}

export async function streamIngestionJob(
  token: string,
  codebaseId: string,
  jobId: string,
  onEvent: (data: { status: string; message: string }) => void
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/codebases/${codebaseId}/ingest/jobs/${jobId}/stream`,
    {
      headers: { Authorization: `Bearer ${token}` },
    }
  )
  if (!res.ok) {
    throw new Error(`Failed to connect to status stream: ${res.statusText}`)
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() ?? ''
      for (const chunk of lines) {
        const match = chunk.match(/^data:\s*(.+)$/m)
        if (match) {
          try {
            const data = JSON.parse(match[1]) as {
              status: string
              message?: string
            }
            onEvent({
              status: data.status,
              message: data.message ?? '',
            })
          } catch {
            // ignore malformed events
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
