export interface UserMe {
  id: string
  email: string
  app_metadata: { role?: string }
}

export interface AdminUser {
  id: string
  email: string | null
  app_metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface Codebase {
  id: string
  user_id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface CodebaseDetail extends Codebase {
  versions?: Array<{
    id: string
    codebase_id: string
    version: number
    upload_source: string
    files_added: number
    files_modified: number
    files_deleted: number
    files_unchanged: number
    created_at: string
  }>
}

export interface CodebaseListResponse {
  codebases: Codebase[]
}

export interface IngestionJobResponse {
  job_id: string
  status: string
  message: string
}
