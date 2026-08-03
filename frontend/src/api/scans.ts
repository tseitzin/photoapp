import { request, requestJson } from './client'

export type ScanStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface ScanRead {
  id: number
  status: ScanStatus
  root_ids: number[] | null
  files_found: number
  files_processed: number
  files_added: number
  files_changed: number
  files_unchanged: number
  files_missing: number
  files_moved: number
  error_count: number
  current_path: string | null
  message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface ScanError {
  id: number
  path: string
  error: string
  created_at: string
}

export interface ScanErrorPage {
  items: ScanError[]
  total: number
  limit: number
  offset: number
}

export const TERMINAL_SCAN_STATUSES: ScanStatus[] = ['completed', 'failed', 'cancelled']

export function startScan(rootIds: number[] | null): Promise<ScanRead> {
  return requestJson<ScanRead>('/api/scans', 'POST', { root_ids: rootIds })
}

export function getScan(id: number): Promise<ScanRead> {
  return request<ScanRead>(`/api/scans/${id}`)
}

export function listScans(limit = 1): Promise<ScanRead[]> {
  return request<ScanRead[]>(`/api/scans?limit=${limit}`)
}

export function cancelScan(id: number): Promise<ScanRead> {
  return requestJson<ScanRead>(`/api/scans/${id}/cancel`, 'POST', {})
}

/** Files the scan could not read — unreadable, corrupt, or permission-denied. */
export function listScanErrors(scanId: number, limit = 100): Promise<ScanErrorPage> {
  return request<ScanErrorPage>(`/api/scans/${scanId}/errors?limit=${limit}`)
}
