import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useLibraryStore } from '../library'
import { listPhotos } from '@/api/photos'
import type { PhotoPage, PhotoRead } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  listPhotos: vi.fn<() => Promise<PhotoPage>>(),
  getFacets: vi
    .fn<() => Promise<{ file_types: never[]; cameras: never[] }>>()
    .mockResolvedValue({ file_types: [], cameras: [] }),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))

const listPhotosMock = vi.mocked(listPhotos)

function page(ids: number[], total: number): PhotoPage {
  return {
    items: ids.map(
      (id): PhotoRead => ({
        id,
        root_id: 1,
        path: `/lib/p${id}.jpg`,
        filename: `p${id}.jpg`,
        ext: 'jpg',
        mime: 'image/jpeg',
        size_bytes: 100,
        width: 10,
        height: 10,
        captured_at: null,
        camera_make: null,
        camera_model: null,
        status: 'active',
        created_at: '2026-01-01T00:00:00Z',
      }),
    ),
    total,
    limit: 100,
    offset: 0,
  }
}

describe('library store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listPhotosMock.mockReset()
  })

  it('loads the first page and reports the total', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 5))
    const store = useLibraryStore()

    await store.reload()

    expect(store.photos).toHaveLength(2)
    expect(store.total).toBe(5)
    expect(store.hasMore).toBe(true)
  })

  it('appends the next page on loadMore and stops at the total', async () => {
    listPhotosMock.mockResolvedValueOnce(page([1, 2], 3))
    const store = useLibraryStore()
    await store.reload()
    listPhotosMock.mockResolvedValueOnce(page([3], 3))

    await store.loadMore()

    expect(store.photos.map((p) => p.id)).toEqual([1, 2, 3])
    expect(store.hasMore).toBe(false)

    await store.loadMore()
    expect(listPhotosMock).toHaveBeenCalledTimes(2)
  })

  it('passes the offset of already-loaded photos when loading more', async () => {
    listPhotosMock.mockResolvedValueOnce(page([1, 2], 4))
    const store = useLibraryStore()
    await store.reload()
    listPhotosMock.mockResolvedValueOnce(page([3, 4], 4))

    await store.loadMore()

    expect(listPhotosMock).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 2 }))
  })

  it('toggling a file-type filter refetches from the start with the filter applied', async () => {
    listPhotosMock.mockResolvedValue(page([1], 1))
    const store = useLibraryStore()

    await store.toggleType('jpeg')

    expect(listPhotosMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ types: ['jpeg'], offset: 0 }),
    )

    await store.toggleType('jpeg')
    expect(listPhotosMock).toHaveBeenLastCalledWith(expect.objectContaining({ types: [] }))
  })

  it('records an error and clears results when the API is unreachable', async () => {
    listPhotosMock.mockRejectedValue(new Error('ECONNREFUSED'))
    const store = useLibraryStore()

    await store.reload()

    expect(store.error).toContain('ECONNREFUSED')
    expect(store.photos).toHaveLength(0)
    expect(store.loading).toBe(false)
  })

  it('counts checked folders without double-counting checked descendants', async () => {
    const store = useLibraryStore()
    store.folders = [
      {
        path: '/lib',
        name: 'lib',
        parent_path: null,
        depth: 0,
        photo_count: 10,
        direct_count: 2,
        has_children: true,
        root_id: 1,
      },
      {
        path: '/lib/2024',
        name: '2024',
        parent_path: '/lib',
        depth: 1,
        photo_count: 8,
        direct_count: 8,
        has_children: false,
        root_id: 1,
      },
    ]

    store.toggleChecked('/lib')
    store.toggleChecked('/lib/2024')

    expect(store.checkedTotals).toEqual({ folders: 2, photos: 10 })
  })
})
