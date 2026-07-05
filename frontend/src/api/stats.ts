import { request } from './client'

export interface Stats {
  photos: number
  storage_bytes: number
  folders: number
  missing: number
  duplicate_photos: number
  reclaimable_bytes: number
  last_scan_at: string | null
  /** Lifetime tallies from the audit log — persist across rescans and rebuilds. */
  deleted_count: number
  space_saved_bytes: number
}

export function getStats(): Promise<Stats> {
  return request<Stats>('/api/stats')
}
