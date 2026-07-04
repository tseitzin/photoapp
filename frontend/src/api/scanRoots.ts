import { request, requestJson } from './client'

export interface ScanRoot {
  id: number
  path: string
  enabled: boolean
  created_at: string
}

export function listScanRoots(): Promise<ScanRoot[]> {
  return request<ScanRoot[]>('/api/scan-roots')
}

export function createScanRoot(path: string): Promise<ScanRoot> {
  return requestJson<ScanRoot>('/api/scan-roots', 'POST', { path })
}

export function updateScanRoot(id: number, enabled: boolean): Promise<ScanRoot> {
  return requestJson<ScanRoot>(`/api/scan-roots/${id}`, 'PATCH', { enabled })
}

export function deleteScanRoot(id: number): Promise<void> {
  return request<void>(`/api/scan-roots/${id}`, { method: 'DELETE' })
}
