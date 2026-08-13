import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useMaintenanceStore } from '../maintenance'
import { useLibraryStore } from '../library'
import { backfillGps } from '@/api/maintenance'
import { listPhotos } from '@/api/photos'
import type { BackfillResult } from '@/api/maintenance'

vi.mock('@/api/maintenance', () => ({
  backfillGps: vi.fn<() => Promise<BackfillResult>>(),
}))
vi.mock('@/api/photos', () => ({
  listPhotos: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 }),
  getFacets: vi.fn<() => Promise<unknown>>().mockResolvedValue({ file_types: [], cameras: [] }),
  markPhotos: vi.fn<() => Promise<unknown>>(),
  unmarkPhotos: vi.fn<() => Promise<unknown>>(),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))

const backfillMock = vi.mocked(backfillGps)

function chunk(overrides: Partial<BackfillResult> = {}): BackfillResult {
  return { processed: 1000, updated: 500, next_after_id: null, remaining: 0, ...overrides }
}

describe('GPS backfill', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    backfillMock.mockReset()
    vi.mocked(listPhotos).mockClear()
  })

  it('keeps going until the server runs out of photos to check', async () => {
    backfillMock
      .mockResolvedValueOnce(chunk({ next_after_id: 1000, remaining: 3000 }))
      .mockResolvedValueOnce(chunk({ next_after_id: 2500, remaining: 1500 }))
      .mockResolvedValueOnce(chunk({ processed: 400, updated: 120, next_after_id: null }))
    const store = useMaintenanceStore()

    await store.run()

    expect(backfillMock).toHaveBeenCalledTimes(3)
    // Third argument is the chunk size — a latency budget, not a batch size, so
    // it is asserted rather than left free. The cursors come from the mocks.
    expect(backfillMock).toHaveBeenNthCalledWith(1, 0, 200)
    expect(backfillMock).toHaveBeenNthCalledWith(2, 1000, 200)
    expect(backfillMock).toHaveBeenNthCalledWith(3, 2500, 200)
    expect(store.processed).toBe(2400)
    expect(store.updated).toBe(1120)
    expect(store.running).toBe(false)
  })

  it('reports what it found', async () => {
    backfillMock.mockResolvedValue(chunk({ processed: 4106, updated: 2340 }))
    const store = useMaintenanceStore()

    await store.run()

    expect(store.summary).toContain('4,106')
    expect(store.summary).toContain('2,340')
  })

  it('stopping keeps the work already done', async () => {
    backfillMock.mockImplementation(() =>
      Promise.resolve(chunk({ next_after_id: 999, remaining: 5000 })),
    )
    const store = useMaintenanceStore()

    const run = store.run()
    store.cancel()
    await run

    expect(backfillMock).toHaveBeenCalledTimes(1)
    expect(store.updated).toBe(500)
    expect(store.running).toBe(false)
  })

  it('refreshes an open library so the new coordinates show up', async () => {
    backfillMock.mockResolvedValue(chunk({ updated: 12 }))
    const library = useLibraryStore()
    await library.reload()
    vi.mocked(listPhotos).mockClear()
    const store = useMaintenanceStore()

    await store.run()

    expect(vi.mocked(listPhotos)).toHaveBeenCalled()
  })

  it('does not reload when nothing gained a location', async () => {
    backfillMock.mockResolvedValue(chunk({ updated: 0 }))
    const library = useLibraryStore()
    await library.reload()
    vi.mocked(listPhotos).mockClear()
    const store = useMaintenanceStore()

    await store.run()

    expect(vi.mocked(listPhotos)).not.toHaveBeenCalled()
  })

  it('surfaces a failure instead of looping forever', async () => {
    backfillMock.mockRejectedValue(new Error('unreadable drive'))
    const store = useMaintenanceStore()

    await store.run()

    expect(store.error).toContain('unreadable drive')
    expect(store.running).toBe(false)
  })

  it('a second click while running is ignored', async () => {
    let release = (): void => {}
    backfillMock.mockImplementationOnce(
      () => new Promise((resolve) => (release = () => resolve(chunk()))),
    )
    const store = useMaintenanceStore()

    const first = store.run()
    await store.run()
    release()
    await first

    expect(backfillMock).toHaveBeenCalledTimes(1)
  })
})
