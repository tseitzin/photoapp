import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request } from '../client'
import { getHealth } from '../health'

function stubFetch(response: Response | Error) {
  const mock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  )
  vi.stubGlobal('fetch', mock)
  return mock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('returns the parsed JSON body for a successful response', async () => {
    stubFetch(new Response(JSON.stringify({ value: 42 }), { status: 200 }))

    await expect(request<{ value: number }>('/api/thing')).resolves.toEqual({ value: 42 })
  })

  it('throws ApiError carrying the HTTP status for a non-2xx response', async () => {
    stubFetch(new Response('nope', { status: 404 }))

    const error = await request('/api/missing').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(404)
  })

  it('throws ApiError with status 0 when the backend is unreachable', async () => {
    stubFetch(new TypeError('fetch failed'))

    const error = await request('/api/health').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(0)
  })

  it('requests the health endpoint at /api/health', async () => {
    const mock = stubFetch(
      new Response(JSON.stringify({ status: 'ok', database: 'ok', version: '0.1.0' }), {
        status: 200,
      }),
    )

    await expect(getHealth()).resolves.toMatchObject({ database: 'ok' })
    expect(String(mock.mock.calls[0]?.[0])).toContain('/api/health')
  })
})
