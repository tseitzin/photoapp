import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useQuarantineStore } from '../quarantine'
import { ApiError } from '@/api/client'
import { deletePhotosPermanently, quarantinePhotos, restorePhotos } from '@/api/files'
import type { BatchResult } from '@/api/files'
import type { PhotoRead } from '@/api/photos'

vi.mock('@/api/files', () => ({
  quarantinePhotos: vi.fn<() => Promise<BatchResult>>(),
  restorePhotos: vi.fn<() => Promise<BatchResult>>(),
  deletePhotosPermanently: vi.fn<() => Promise<BatchResult>>(),
  listFileOperations: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 }),
}))
vi.mock('@/api/duplicates', () => ({
  listMarkedForRemoval: vi.fn<() => Promise<PhotoRead[]>>().mockResolvedValue([]),
}))
vi.mock('@/api/photos', () => ({
  listPhotos: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 }),
  getFacets: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ file_types: [], cameras: [] }),
  markPhotos: vi.fn<() => Promise<unknown>>(),
  unmarkPhotos: vi.fn<() => Promise<unknown>>(),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))

import { listMarkedForRemoval } from '@/api/duplicates'
import { getFacets, listPhotos } from '@/api/photos'
import { listFolders } from '@/api/folders'
import { useLibraryStore } from '../library'

const quarantineMock = vi.mocked(quarantinePhotos)
const restoreMock = vi.mocked(restorePhotos)
const deleteMock = vi.mocked(deletePhotosPermanently)
const markedMock = vi.mocked(listMarkedForRemoval)

function photo(id: number): PhotoRead {
  return {
    id,
    root_id: 1,
    path: `/lib/p${id}.jpg`,
    filename: `p${id}.jpg`,
    ext: 'jpg',
    mime: 'image/jpeg',
    size_bytes: 1000,
    width: 10,
    height: 10,
    captured_at: null,
    camera_make: null,
    camera_model: null,
    status: 'active',
    marked_for_deletion: false,
    created_at: '2026-01-01T00:00:00Z',
  }
}

const OK_BATCH: BatchResult = { batch_id: 'b1', succeeded: 2, failed: 0, results: [] }

describe('quarantine store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    quarantineMock.mockReset()
    restoreMock.mockReset()
    deleteMock.mockReset()
    markedMock.mockResolvedValue([photo(1), photo(2)])
  })

  it('applyRemovals quarantines all marked photos and reloads', async () => {
    quarantineMock.mockResolvedValue(OK_BATCH)
    const store = useQuarantineStore()
    await store.load()

    const ok = await store.applyRemovals()

    expect(ok).toBe(true)
    expect(quarantineMock).toHaveBeenCalledWith([1, 2], false)
    expect(store.lastBatch?.succeeded).toBe(2)
  })

  it('a 409 group-wipe response raises the force warning instead of an error', async () => {
    quarantineMock.mockRejectedValue(new ApiError(409, 'would remove every remaining photo'))
    const store = useQuarantineStore()
    await store.load()

    const ok = await store.applyRemovals()

    expect(ok).toBe(false)
    expect(store.forceWarning).toContain('every remaining photo')
    expect(store.error).toBeNull()
  })

  it('retrying with force passes force=true', async () => {
    quarantineMock.mockResolvedValue(OK_BATCH)
    const store = useQuarantineStore()
    await store.load()

    await store.applyRemovals(true)

    expect(quarantineMock).toHaveBeenCalledWith([1, 2], true)
  })

  it('restore posts the selected ids', async () => {
    restoreMock.mockResolvedValue(OK_BATCH)
    const store = useQuarantineStore()

    await store.restore([5, 6])

    expect(restoreMock).toHaveBeenCalledWith([5, 6])
  })

  it('permanent delete always sends confirm=true from the store', async () => {
    deleteMock.mockResolvedValue(OK_BATCH)
    const store = useQuarantineStore()

    await store.deletePermanently([9])

    expect(deleteMock).toHaveBeenCalledWith([9], true)
  })

  it('non-409 failures surface as errors', async () => {
    quarantineMock.mockRejectedValue(new ApiError(0, 'Cannot reach the library service'))
    const store = useQuarantineStore()
    await store.load()

    const ok = await store.applyRemovals()

    expect(ok).toBe(false)
    expect(store.error).toContain('Cannot reach')
    expect(store.forceWarning).toBeNull()
  })

  it('deleting photos refreshes the library that was showing them', async () => {
    // Otherwise deleted photos stay on the grid with broken thumbnails and a
    // wrong total until the user reloads by hand.
    deleteMock.mockResolvedValue(OK_BATCH)
    const library = useLibraryStore()
    await library.reload() // the user has opened the Library
    const store = useQuarantineStore()
    vi.mocked(listPhotos).mockClear()
    vi.mocked(getFacets).mockClear()
    vi.mocked(listFolders).mockClear()

    await store.deletePermanently([9])

    expect(vi.mocked(listPhotos)).toHaveBeenCalled()
    expect(vi.mocked(getFacets)).toHaveBeenCalled() // facets were never refreshed before
    expect(vi.mocked(listFolders)).toHaveBeenCalled()
  })

  it('quarantining and restoring refresh the library too', async () => {
    quarantineMock.mockResolvedValue(OK_BATCH)
    restoreMock.mockResolvedValue(OK_BATCH)
    const library = useLibraryStore()
    await library.reload()
    const store = useQuarantineStore()
    await store.load()

    vi.mocked(getFacets).mockClear()
    await store.applyRemovals()
    expect(vi.mocked(getFacets)).toHaveBeenCalled()

    vi.mocked(getFacets).mockClear()
    await store.restore([1])
    expect(vi.mocked(getFacets)).toHaveBeenCalled()
  })

  it('leaves an unopened library alone', async () => {
    // Nothing has been loaded yet, so there is nothing stale to refresh.
    deleteMock.mockResolvedValue(OK_BATCH)
    const store = useQuarantineStore()
    vi.mocked(getFacets).mockClear()

    await store.deletePermanently([9])

    expect(vi.mocked(getFacets)).not.toHaveBeenCalled()
  })

  it('a failing library refresh does not mask a successful deletion', async () => {
    deleteMock.mockResolvedValue(OK_BATCH)
    const library = useLibraryStore()
    await library.reload()
    const store = useQuarantineStore()
    vi.mocked(listPhotos).mockRejectedValueOnce(new Error('network blip'))

    await store.deletePermanently([9])

    expect(store.lastBatch?.succeeded).toBe(2)
  })
})
