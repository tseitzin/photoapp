import { request, requestJson } from './client'

export type OrganizeMode = 'keep' | 'date' | 'camera'
export type OrganizeStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface OrganizeRequest {
  folders: string[]
  destination: string
  mode: OrganizeMode
  rename: boolean
  skip_duplicates: boolean
}

export interface RenameExample {
  old: string
  new: string
}

export interface OrganizePreview {
  total: number
  planned: number
  duplicates_in_set: number
  duplicates_skipped: number
  already_organized: number
  undated: number
  est_bytes: number
  example_paths: string[]
  rename_example: RenameExample | null
}

export interface OrganizeRun {
  id: number
  status: OrganizeStatus
  params: OrganizeRequest
  batch_id: string
  total: number
  planned: number
  moved: number
  skipped_duplicates: number
  already_organized: number
  undated: number
  failed_count: number
  est_bytes: number
  message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export const TERMINAL_ORGANIZE_STATUSES: OrganizeStatus[] = ['completed', 'failed']

export function previewOrganize(req: OrganizeRequest): Promise<OrganizePreview> {
  return requestJson<OrganizePreview>('/api/organize/preview', 'POST', req)
}

export function startOrganize(req: OrganizeRequest): Promise<OrganizeRun> {
  return requestJson<OrganizeRun>('/api/organize', 'POST', req)
}

export function getOrganizeRun(id: number): Promise<OrganizeRun> {
  return request<OrganizeRun>(`/api/organize/${id}`)
}

export function listOrganizeRuns(limit = 1): Promise<OrganizeRun[]> {
  return request<OrganizeRun[]>(`/api/organize?limit=${limit}`)
}
