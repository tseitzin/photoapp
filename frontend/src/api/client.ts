const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8003'

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
      headers: { Accept: 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError(0, `Cannot reach the library service at ${BASE_URL}`)
  }
  if (!response.ok) {
    throw new ApiError(response.status, `${init?.method ?? 'GET'} ${path} → ${response.status}`)
  }
  return (await response.json()) as T
}
