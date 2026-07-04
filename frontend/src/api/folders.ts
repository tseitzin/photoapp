import { request } from './client'

export interface FolderNode {
  path: string
  name: string
  parent_path: string | null
  depth: number
  photo_count: number
  direct_count: number
  has_children: boolean
  root_id: number
}

export function listFolders(): Promise<FolderNode[]> {
  return request<FolderNode[]>('/api/folders')
}
