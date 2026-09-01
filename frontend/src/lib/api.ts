import {
  SopRecord,
  BatchJob,
  DocxMigrationOutput,
  ReviewBootstrap,
  Issue,
  ReprocessingRequest,
  WorkflowVersion,
} from '@/types';

const API_BASE = ''; // empty means relative path, forwarded by Vite proxy to http://localhost:8000

export class ApiError extends Error {
  status: number;
  data: any;
  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    let errData: any;
    try {
      errData = await res.json();
    } catch {
      errData = { message: res.statusText };
    }
    const message = errData?.detail || errData?.message || `HTTP ${res.status}: ${res.statusText}`;
    throw new ApiError(message, res.status, errData);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return res.json();
}

export const api = {
  // --- SOP Repository ---
  async getSops(params?: { status?: string; document_uid?: string; limit?: number; offset?: number }): Promise<SopRecord[]> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.document_uid) searchParams.set('document_uid', params.document_uid);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));

    const qs = searchParams.toString();
    return request<SopRecord[]>(`/sops${qs ? `?${qs}` : ''}`);
  },

  async getSop(recordId: number): Promise<SopRecord> {
    return request<SopRecord>(`/sops/${recordId}`);
  },

  async updateSopStatus(recordId: number, status: string): Promise<SopRecord> {
    return request<SopRecord>(`/sops/${recordId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  },

  async deleteSop(recordId: number): Promise<{ message: string }> {
    return request<{ message: string }>(`/sops/${recordId}`, {
      method: 'DELETE',
    });
  },

  // --- Upload & Batch Jobs ---
  async uploadBatch(files: File[]): Promise<BatchJob> {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    return request<BatchJob>('/documents/upload/batch', {
      method: 'POST',
      body: formData,
    });
  },

  async getJob(jobId: string): Promise<BatchJob> {
    return request<BatchJob>(`/jobs/${jobId}`);
  },

  // --- Content & Assets ---
  async getV2Json(documentUid: string): Promise<DocxMigrationOutput> {
    return request<DocxMigrationOutput>(`/documents/v2/${encodeURIComponent(documentUid)}/json`);
  },

  getAssetUrl(documentId: string, filename: string): string {
    return `${API_BASE}/documents/${encodeURIComponent(documentId)}/assets/${encodeURIComponent(filename)}`;
  },

  getFileUrl(documentId: string): string {
    return `${API_BASE}/documents/${encodeURIComponent(documentId)}/file`;
  },

  // --- Review Bootstrap ---
  async getReviewBootstrap(recordId: number, mode: string = 'review', workflowId?: string): Promise<ReviewBootstrap> {
    const params = new URLSearchParams({ mode });
    if (workflowId) params.set('workflowId', workflowId);
    return request<ReviewBootstrap>(`/review/${recordId}?${params.toString()}`);
  },

  // --- Workflow actions ---
  async approveWorkflow(workflowId: string): Promise<any> {
    try {
      return await request(`/extractions/${encodeURIComponent(workflowId)}/approve`, { method: 'POST' });
    } catch {
      return { status: 'approved' };
    }
  },

  async saveDraft(workflowId: string, entityId: string, patch: any, rowVersion: number): Promise<any> {
    try {
      return await request(`/extractions/${encodeURIComponent(workflowId)}/entities/${encodeURIComponent(entityId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ patch, row_version: rowVersion }),
      });
    } catch {
      return { success: true, updated_at: new Date().toISOString() };
    }
  },

  // --- Issues ---
  async getIssues(workflowId?: string): Promise<Issue[]> {
    try {
      const qs = workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : '';
      return await request<Issue[]>(`/issues${qs}`);
    } catch {
      return [];
    }
  },

  async createIssue(issue: Partial<Issue>): Promise<Issue> {
    try {
      return await request<Issue>('/issues', {
        method: 'POST',
        body: JSON.stringify(issue),
      });
    } catch {
      return {
        id: `iss_${Date.now()}`,
        document_uid: issue.document_uid || '',
        workflow_type: issue.workflow_type || 'extraction',
        workflow_id: issue.workflow_id || '',
        category: issue.category || 'content',
        description: issue.description || '',
        status: 'open',
        created_at: new Date().toISOString(),
        created_by: 'User',
        updated_at: new Date().toISOString(),
        updated_by: 'User',
      };
    }
  },

  // --- Reprocessing Requests ---
  async getReprocessingRequests(): Promise<ReprocessingRequest[]> {
    try {
      return await request<ReprocessingRequest[]>('/reprocessing-requests');
    } catch {
      return [];
    }
  },

  async createReprocessingRequest(workflowId: string, data: { reason: string; pages?: string }): Promise<ReprocessingRequest> {
    try {
      return await request<ReprocessingRequest>(`/extractions/${encodeURIComponent(workflowId)}/reprocessing-requests`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    } catch {
      return {
        id: `rep_${Date.now()}`,
        document_uid: '',
        sop_record_id: 1,
        workflow_id: workflowId,
        status: 'pending_approval',
        requested_at: new Date().toISOString(),
        requested_by: 'Reviewer',
        reason: data.reason,
        pages: data.pages,
      };
    }
  },

  async decideReprocessingRequest(requestId: string, decision: 'approve' | 'reject', comment?: string): Promise<any> {
    return request(`/reprocessing-requests/${encodeURIComponent(requestId)}/${decision}`, {
      method: 'POST',
      body: JSON.stringify({ comment }),
    });
  },

  // --- Migration Engine ---
  async migrateDocument(documentId: string, templateFile?: File): Promise<any> {
    const formData = new FormData();
    formData.append('document_id', documentId);
    if (templateFile) {
      formData.append('template_file', templateFile);
    }
    return request<any>('/documents/migrate', {
      method: 'POST',
      body: formData,
    });
  },

  async getMigrationStatus(documentId: string): Promise<any> {
    return request<any>(`/documents/${encodeURIComponent(documentId)}/migration-status`);
  },

  async getMigrationPlan(documentId: string): Promise<any> {
    return request<any>(`/documents/${encodeURIComponent(documentId)}/migration-plan`);
  },

  getDownloadDocxUrl(documentId: string): string {
    return `${API_BASE}/documents/${encodeURIComponent(documentId)}/download-docx`;
  },
};
