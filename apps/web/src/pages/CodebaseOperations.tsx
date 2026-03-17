import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  deleteCodebase,
  getCodebase,
  ingestCodebase,
  streamIngestionJob,
} from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import type { CodebaseDetail } from '@/types/api'

export function CodebaseOperations() {
  const { id } = useParams<{ id: string }>()
  const { session } = useAuth()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [codebase, setCodebase] = useState<CodebaseDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [ingestionStatus, setIngestionStatus] = useState<{
    job_id: string
    status: string
    message: string
  } | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  const token = session?.access_token

  const loadCodebase = useCallback(async () => {
    if (!token || !id) return
    setLoading(true)
    setError(null)
    try {
      const data = await getCodebase(token, id)
      setCodebase(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load codebase')
      setCodebase(null)
    } finally {
      setLoading(false)
    }
  }, [token, id])

  useEffect(() => {
    loadCodebase()
  }, [loadCodebase])

  async function handleDelete() {
    if (!token || !id || !confirm('Delete this codebase? This cannot be undone.'))
      return
    try {
      await deleteCodebase(token, id)
      navigate('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete')
    }
  }

  function handleFileSelect(file: File | null) {
    if (!file) {
      setSelectedFile(null)
      setIngestionStatus(null)
      return
    }
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setIngestionStatus({
        job_id: '',
        status: 'error',
        message: 'Please select a .zip file.',
      })
      setSelectedFile(null)
      return
    }
    setSelectedFile(file)
    setIngestionStatus(null)
  }

  async function handleIngest() {
    if (!token || !id || !selectedFile || isUploading) return
    setIsUploading(true)
    setIngestionStatus(null)
    try {
      const res = await ingestCodebase(token, id, selectedFile)
      setIngestionStatus(res)
      await streamIngestionJob(token, id, res.job_id, (data) => {
        setIngestionStatus((prev) =>
          prev ? { ...prev, status: data.status, message: data.message } : null
        )
      })
      setSelectedFile(null)
    } catch (err) {
      setIngestionStatus({
        job_id: '',
        status: 'error',
        message: err instanceof Error ? err.message : 'Upload failed',
      })
    } finally {
      setIsUploading(false)
    }
  }

  if (loading || !codebase) {
    return (
      <div className="py-8">
        {loading ? (
          <div className="text-slate-500">Loading…</div>
        ) : (
          <div className="text-red-600">{error || 'Codebase not found'}</div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900">{codebase.name}</h2>
        <button
          onClick={handleDelete}
          className="rounded-lg border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
        >
          Delete Codebase
        </button>
      </header>

      {codebase.description && (
        <p className="text-slate-600 text-sm">{codebase.description}</p>
      )}

      {/* Ingest */}
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900 mb-2">Ingest</h3>
        <p className="text-slate-600 text-sm mb-4">
          Upload a ZIP archive to index your codebase.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
        />
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
          onDrop={(e) => {
            e.preventDefault()
            e.stopPropagation()
            const file = e.dataTransfer.files?.[0]
            handleFileSelect(file ?? null)
          }}
          className="rounded-lg border-2 border-dashed border-slate-200 bg-slate-50 px-6 py-8 text-center cursor-pointer hover:border-slate-300 hover:bg-slate-100 transition-colors"
        >
          {selectedFile ? (
            <p className="text-slate-700 font-medium">{selectedFile.name}</p>
          ) : (
            <p className="text-slate-500">
              Drag and drop a .zip file here, or click to select
            </p>
          )}
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleIngest}
            disabled={!selectedFile || isUploading}
            className="rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isUploading ? 'Ingesting…' : 'Start Ingestion'}
          </button>
        </div>
        {ingestionStatus && (
          <div
            className={`mt-4 rounded-lg px-3 py-2 text-sm ${
              ingestionStatus.status === 'completed'
                ? 'bg-green-50 text-green-800'
                : ingestionStatus.status === 'failed' ||
                    ingestionStatus.status === 'error'
                  ? 'bg-red-50 text-red-700'
                  : 'bg-slate-100 text-slate-700'
            }`}
          >
            {ingestionStatus.status === 'queued' && (
              <span>Queued for indexing…</span>
            )}
            {ingestionStatus.status === 'processing' && (
              <span>
                Indexing in progress…
                {ingestionStatus.message && ` ${ingestionStatus.message}`}
              </span>
            )}
            {ingestionStatus.status === 'completed' && (
              <span>Ingestion complete.</span>
            )}
            {(ingestionStatus.status === 'failed' ||
              ingestionStatus.status === 'error') && (
              <span>
                Ingestion failed
                {ingestionStatus.message && `: ${ingestionStatus.message}`}
              </span>
            )}
            {!['queued', 'processing', 'completed', 'failed', 'error'].includes(
              ingestionStatus.status
            ) && (
              <span>
                {ingestionStatus.message || ingestionStatus.status}
              </span>
            )}
          </div>
        )}
      </section>

      {/* Placeholder: Query */}
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900 mb-2">Query</h3>
        <p className="text-slate-600 text-sm mb-4">
          Run a natural-language query against your indexed code.
        </p>
        <div className="rounded-lg border-2 border-dashed border-slate-200 bg-slate-50 px-6 py-8 text-center text-slate-500">
          Coming soon
        </div>
      </section>
    </div>
  )
}
