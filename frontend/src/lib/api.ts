import type { BatchJob, MigrationDocument, SopListResponse, SopRecord, SopStatus } from '../types'

/** Base URL of the FastAPI backend. Override via VITE_API_BASE for other environments. */
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** Structured error raised for any non-2xx response, carrying the backend's own message. */
export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** Shared response handling: FastAPI's AppError/validation handlers return a consistent shape. */
async function handleResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T
  }

  let message = `Request failed with status ${response.status}`
  let detail: unknown
  try {
    const body = await response.json()
    message = body.message ?? message
    detail = body.detail
  } catch {
    // Response body wasn't JSON (e.g. a proxy/network error page) — keep the default message.
  }
  throw new ApiError(message, response.status, detail)
}

/** List SOP extraction-run records, newest first. */
export async function listSops(): Promise<SopListResponse> {
  const response = await fetch(`${API_BASE}/sops?limit=1000`)
  return handleResponse<SopListResponse>(response)
}

/** Fetch a single SOP record by its surrogate id. */
export async function getSop(recordId: number): Promise<SopRecord> {
  const response = await fetch(`${API_BASE}/sops/${recordId}`)
  return handleResponse<SopRecord>(response)
}

/** Fetch a document's fully processed section/element content (v2 export). */
export async function getDocumentContent(documentUid: string): Promise<MigrationDocument> {
  const response = await fetch(`${API_BASE}/documents/v2/${encodeURIComponent(documentUid)}/json`)
  return handleResponse<MigrationDocument>(response)
}

/** Resolve a relative asset path (e.g. from image_path/icon.path) into a fetchable URL. */
export function assetUrl(path: string): string {
  return `${API_BASE}${path}`
}

/** Update a SOP record's review status (in_review / approved / rejected). */
export async function updateSopStatus(recordId: number, status: SopStatus) {
  const response = await fetch(`${API_BASE}/sops/${recordId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
  return handleResponse(response)
}

/** Delete a SOP record. The backend also best-effort removes its files if no other version references them. */
export async function deleteSop(recordId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/sops/${recordId}`, { method: 'DELETE' })
  if (response.ok) return
  await handleResponse(response)
}

/** Upload one or more PDF/DOCX files and enqueue a batch extraction job. */
export async function uploadBatch(files: File[]): Promise<BatchJob> {
  const formData = new FormData()
  for (const file of files) {
    formData.append('files', file)
  }
  const response = await fetch(`${API_BASE}/documents/upload/batch`, {
    method: 'POST',
    body: formData,
  })
  return handleResponse<BatchJob>(response)
}

/** Poll the current state of a batch job (progress, per-document status). */
export async function getJob(jobId: string): Promise<BatchJob> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}`)
  return handleResponse<BatchJob>(response)
}
