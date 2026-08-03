import { API_BASE_URL, request, requestJson } from './client'

export type PhotoStatus = 'active' | 'missing' | 'quarantined'
export type PhotoSort =
  | 'captured_desc'
  | 'captured_asc'
  | 'name_asc'
  | 'name_desc'
  | 'size_desc'
  | 'size_asc'
  | 'added_desc'

export interface PhotoRead {
  id: number
  root_id: number
  path: string
  filename: string
  ext: string
  mime: string
  size_bytes: number
  width: number | null
  height: number | null
  captured_at: string | null
  camera_make: string | null
  camera_model: string | null
  // GPS decimal degrees; optional so test fixtures predating GPS stay valid.
  latitude?: number | null
  longitude?: number | null
  // Nearest known place to those coordinates, from offline reverse geocoding.
  // place_distance_km is how far that place is: the nearest town can be well
  // away, so the UI says "near X" rather than claiming the photo was taken there.
  city?: string | null
  region?: string | null
  country?: string | null
  place_distance_km?: number | null
  status: PhotoStatus
  marked_for_deletion: boolean
  created_at: string
}

export interface PhotoDetail extends PhotoRead {
  sha256: string | null
  mtime_ns: number
  exif: Record<string, unknown> | null
  last_error: string | null
  updated_at: string
}

export interface PhotoPage {
  items: PhotoRead[]
  total: number
  limit: number
  offset: number
}

export interface FacetValue {
  value: string
  count: number
}

export interface Facets {
  file_types: FacetValue[]
  cameras: FacetValue[]
}

export interface PhotoQuery {
  limit?: number
  offset?: number
  folder?: string | null
  types?: string[]
  cameras?: string[]
  q?: string
  sort?: PhotoSort
  status?: PhotoStatus
}

export function listPhotos(query: PhotoQuery = {}): Promise<PhotoPage> {
  const params = new URLSearchParams()
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset !== undefined) params.set('offset', String(query.offset))
  if (query.folder) params.set('folder', query.folder)
  for (const type of query.types ?? []) params.append('type', type)
  for (const camera of query.cameras ?? []) params.append('camera', camera)
  if (query.q) params.set('q', query.q)
  if (query.sort) params.set('sort', query.sort)
  if (query.status) params.set('status', query.status)
  const suffix = params.size ? `?${params.toString()}` : ''
  return request<PhotoPage>(`/api/photos${suffix}`)
}

export function getPhoto(id: number): Promise<PhotoDetail> {
  return request<PhotoDetail>(`/api/photos/${id}`)
}

export interface SimilarPhoto {
  photo: PhotoRead
  /** Hamming distance between the perceptual hashes; lower is closer. */
  distance: number
  similarity_pct: number
}

/**
 * Visually similar photos — resized, recompressed or re-encoded variants.
 * pHash does not find crops or edits.
 */
export function listSimilarPhotos(id: number, limit = 12): Promise<SimilarPhoto[]> {
  return request<SimilarPhoto[]>(`/api/photos/${id}/similar?limit=${limit}`)
}

export function getFacets(): Promise<Facets> {
  return request<Facets>('/api/photos/facets')
}

export function markPhotos(photoIds: number[]): Promise<{ marked: boolean; affected: number }> {
  return requestJson('/api/photos/mark', 'POST', { photo_ids: photoIds })
}

export function unmarkPhotos(photoIds: number[]): Promise<{ marked: boolean; affected: number }> {
  return requestJson('/api/photos/unmark', 'POST', { photo_ids: photoIds })
}

export function thumbnailUrl(id: number): string {
  return `${API_BASE_URL}/api/photos/${id}/thumbnail`
}

export function previewUrl(id: number): string {
  return `${API_BASE_URL}/api/photos/${id}/preview`
}
