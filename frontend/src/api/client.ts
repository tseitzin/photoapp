export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8003'
const BASE_URL = API_BASE_URL

export class ApiError extends Error {
  /** HTTP status; 0 when the backend could not be reached at all. */
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      // Never serve API JSON from the HTTP cache: after a mutation (e.g.
      // quarantining) the next GET of the same URL must reflect the new state,
      // not a stale cached copy. (Image URLs use <img>, so they keep their own
      // immutable caching.)
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError(0, `Cannot reach the library service at ${BASE_URL}`)
  }
  if (!response.ok) {
    let detail = ''
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? ''
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      response.status,
      detail || `${init?.method ?? 'GET'} ${path} → ${response.status}`,
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function requestJson<T>(path: string, method: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
