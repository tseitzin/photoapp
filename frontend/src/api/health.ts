import { request } from './client'

export interface Health {
  status: 'ok'
  database: 'ok' | 'unavailable'
  version: string
}

export function getHealth(): Promise<Health> {
  return request<Health>('/api/health')
}
