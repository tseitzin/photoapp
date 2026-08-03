import { requestJson } from './client'

export interface BackfillResult {
  processed: number
  updated: number
  /** Pass back as after_id to continue; null means the sweep is done. */
  next_after_id: number | null
  remaining: number
}

/**
 * One chunk of the GPS backfill.
 *
 * Photos indexed before GPS extraction existed have null coordinates, and
 * rescans skip unchanged files, so they would never gain them on their own.
 * The server reads only each file's EXIF header — no decode, no hashing — and
 * walks the library by id cursor; call again with next_after_id until it is
 * null.
 */
export function backfillGps(afterId = 0, limit = 1000): Promise<BackfillResult> {
  return requestJson<BackfillResult>('/api/maintenance/backfill-gps', 'POST', {
    after_id: afterId,
    limit,
  })
}
