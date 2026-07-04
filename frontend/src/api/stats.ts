import { request } from './client'

export interface Stats {
  photos: number
  storage_bytes: number
  folders: number
  missing: number
  duplicate_photos: number
  reclaimable_bytes: number
  last_scan_at: string | null
}

export function getStats(): Promise<Stats> {
  return request<Stats>('/api/stats')
}
