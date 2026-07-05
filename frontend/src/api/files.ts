import { request, requestJson } from './client'

export interface ItemResult {
  photo_id: number
  ok: boolean
  error: string | null
}

export interface BatchResult {
  batch_id: string
  succeeded: number
  failed: number
  results: ItemResult[]
}

export interface FileOperation {
  id: number
  photo_id: number | null
  op: 'quarantine' | 'restore' | 'delete'
  src_path: string
  dest_path: string | null
  batch_id: string
  performed_at: string
}

export interface FileOperationPage {
  items: FileOperation[]
  total: number
  limit: number
  offset: number
}

export function quarantinePhotos(photoIds: number[], force = false): Promise<BatchResult> {
  return requestJson<BatchResult>('/api/quarantine', 'POST', { photo_ids: photoIds, force })
}

export function restorePhotos(photoIds: number[]): Promise<BatchResult> {
  return requestJson<BatchResult>('/api/quarantine/restore', 'POST', { photo_ids: photoIds })
}

export function deletePhotosPermanently(
  photoIds: number[],
  confirm: boolean,
): Promise<BatchResult> {
  return requestJson<BatchResult>('/api/quarantine/delete', 'POST', {
    photo_ids: photoIds,
    confirm,
  })
}

export function listFileOperations(limit = 50, offset = 0): Promise<FileOperationPage> {
  return request<FileOperationPage>(`/api/file-operations?limit=${limit}&offset=${offset}`)
}

/** Reset the lifetime deletion tally and clear history for removed files. */
export function resetDeletionHistory(): Promise<{ cleared: number }> {
  return requestJson<{ cleared: number }>('/api/file-operations/reset', 'POST', {})
}
