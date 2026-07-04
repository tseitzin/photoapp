import { request, requestJson } from './client'
import type { PhotoRead } from './photos'

export type DuplicateKind = 'exact' | 'similar'
export type GroupStatus = 'pending' | 'reviewed' | 'dismissed'
export type Decision = 'keep' | 'remove' | 'undecided'

export interface DuplicateMember {
  photo: PhotoRead
  similarity_pct: number
  decision: 'keep' | 'remove' | null
}

export interface DuplicateGroup {
  id: number
  kind: DuplicateKind
  status: GroupStatus
  keeper_photo_id: number | null
  members: DuplicateMember[]
  reclaimable_bytes: number
  created_at: string
}

export interface DuplicateGroupPage {
  items: DuplicateGroup[]
  total: number
  limit: number
  offset: number
}

export interface DuplicateSummary {
  groups: number
  pending_groups: number
  reviewed_groups: number
  dismissed_groups: number
  exact_groups: number
  similar_groups: number
  member_photos: number
  marked_remove_count: number
  marked_remove_bytes: number
}

export interface GroupQuery {
  kind?: DuplicateKind
  status?: GroupStatus
  limit?: number
  offset?: number
}

export function listGroups(query: GroupQuery = {}): Promise<DuplicateGroupPage> {
  const params = new URLSearchParams()
  if (query.kind) params.set('kind', query.kind)
  if (query.status) params.set('status', query.status)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset !== undefined) params.set('offset', String(query.offset))
  const suffix = params.size ? `?${params.toString()}` : ''
  return request<DuplicateGroupPage>(`/api/duplicates/groups${suffix}`)
}

export function decideGroup(
  groupId: number,
  decisions: { photo_id: number; decision: Decision }[],
): Promise<DuplicateGroup> {
  return requestJson<DuplicateGroup>(`/api/duplicates/groups/${groupId}/decisions`, 'POST', {
    decisions,
  })
}

export function dismissGroup(groupId: number): Promise<DuplicateGroup> {
  return requestJson<DuplicateGroup>(`/api/duplicates/groups/${groupId}/dismiss`, 'POST', {})
}

export function getDuplicateSummary(): Promise<DuplicateSummary> {
  return request<DuplicateSummary>('/api/duplicates/summary')
}
