import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useLibraryStore } from '../library'
import { listPhotos, markPhotos, unmarkPhotos } from '@/api/photos'
import type { PhotoPage, PhotoRead } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  listPhotos: vi.fn<() => Promise<PhotoPage>>(),
  getFacets: vi
    .fn<() => Promise<{ file_types: never[]; cameras: never[] }>>()
    .mockResolvedValue({ file_types: [], cameras: [] }),
  markPhotos: vi.fn<() => Promise<unknown>>().mockResolvedValue({ marked: true, affected: 1 }),
  unmarkPhotos: vi.fn<() => Promise<unknown>>().mockResolvedValue({ marked: false, affected: 1 }),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))

const listPhotosMock = vi.mocked(listPhotos)
const markMock = vi.mocked(markPhotos)
const unmarkMock = vi.mocked(unmarkPhotos)

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
        marked_for_deletion: false,
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
    markMock.mockClear()
    markMock.mockResolvedValue({ marked: true, affected: 1 })
    unmarkMock.mockClear()
  })

  it('loads the first page and reports the total and page count', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 5))
    const store = useLibraryStore()

    await store.reload()

    expect(store.photos).toHaveLength(2)
    expect(store.total).toBe(5)
    expect(store.totalPages).toBe(1)
    expect(listPhotosMock).toHaveBeenCalledWith(expect.objectContaining({ limit: 100, offset: 0 }))
  })

  it('reports the page count for the selected page size', async () => {
    listPhotosMock.mockResolvedValue(page([1], 5575))
    const store = useLibraryStore()

    await store.reload() // default 100/page
    expect(store.totalPages).toBe(56) // ceil(5575 / 100)

    await store.setPageSize(1000)
    expect(store.totalPages).toBe(6) // 5575 over 1000/page

    await store.setPageSize(500)
    expect(store.totalPages).toBe(12) // 5575 over 500/page

    await store.setPageSize(250)
    expect(store.totalPages).toBe(23) // ceil(5575 / 250)
  })

  it('nextPage advances the offset and clamps at the last page', async () => {
    listPhotosMock.mockResolvedValue(page([1], 250)) // 250 / 100 = 3 pages
    const store = useLibraryStore()
    await store.reload()
    expect(store.totalPages).toBe(3)

    await store.nextPage()
    expect(store.page).toBe(1)
    expect(listPhotosMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 100, offset: 100 }),
    )

    await store.nextPage()
    expect(store.page).toBe(2)
    await store.nextPage() // already on the last page — no change, no fetch
    expect(store.page).toBe(2)
    expect(listPhotosMock).toHaveBeenCalledTimes(3)
  })

  it('prevPage does nothing on the first page', async () => {
    listPhotosMock.mockResolvedValue(page([1], 50))
    const store = useLibraryStore()
    await store.reload()

    await store.prevPage()

    expect(store.page).toBe(0)
    expect(listPhotosMock).toHaveBeenCalledTimes(1)
  })

  it('changing the page size refetches from page 0 with the new limit', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 900))
    const store = useLibraryStore()
    await store.reload()
    await store.nextPage()

    await store.setPageSize(500)

    expect(store.page).toBe(0)
    expect(listPhotosMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 500, offset: 0 }),
    )
  })

  it('"all" pages through in 1000-row chunks until the whole library is loaded', async () => {
    // total 2500 spans three chunks; each mocked response only needs the right total.
    listPhotosMock
      .mockResolvedValueOnce(page([1], 2500))
      .mockResolvedValueOnce(page([2], 2500))
      .mockResolvedValueOnce(page([3], 2500))
    const store = useLibraryStore()

    await store.setPageSize('all')

    expect(listPhotosMock).toHaveBeenCalledTimes(3)
    expect(listPhotosMock).toHaveBeenNthCalledWith(1, expect.objectContaining({ limit: 1000, offset: 0 }))
    expect(listPhotosMock).toHaveBeenNthCalledWith(2, expect.objectContaining({ limit: 1000, offset: 1000 }))
    expect(listPhotosMock).toHaveBeenNthCalledWith(3, expect.objectContaining({ limit: 1000, offset: 2000 }))
    expect(store.photos.map((p) => p.id)).toEqual([1, 2, 3])
    expect(store.totalPages).toBe(1)
  })

  it('toggling a file-type filter refetches from page 0 with the filter applied', async () => {
    listPhotosMock.mockResolvedValue(page([1], 1))
    const store = useLibraryStore()

    await store.toggleType('jpeg')

    expect(listPhotosMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ types: ['jpeg'], offset: 0 }),
    )

    await store.toggleType('jpeg')
    expect(listPhotosMock).toHaveBeenLastCalledWith(expect.objectContaining({ types: [] }))
  })

  it('selecting a folder filters the grid to it and reselecting clears it', async () => {
    listPhotosMock.mockResolvedValue(page([1], 1))
    const store = useLibraryStore()

    await store.setFolder('/lib/Updated/2006')

    expect(store.activeFolder).toBe('/lib/Updated/2006')
    expect(listPhotosMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ folder: '/lib/Updated/2006', offset: 0 }),
    )

    await store.setFolder('/lib/Updated/2006') // same folder toggles back to all
    expect(store.activeFolder).toBeNull()
    expect(listPhotosMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ folder: undefined }),
    )
  })

  it('clearing filters also clears the folder selection', async () => {
    listPhotosMock.mockResolvedValue(page([1], 1))
    const store = useLibraryStore()
    await store.setFolder('/lib/Updated')
    expect(store.hasActiveFilters).toBe(true)

    await store.clearFilters()

    expect(store.activeFolder).toBeNull()
    expect(store.hasActiveFilters).toBe(false)
  })

  it('records an error and clears results when the API is unreachable', async () => {
    listPhotosMock.mockRejectedValue(new Error('ECONNREFUSED'))
    const store = useLibraryStore()

    await store.reload()

    expect(store.error).toContain('ECONNREFUSED')
    expect(store.photos).toHaveLength(0)
    expect(store.total).toBe(0)
    expect(store.loading).toBe(false)
  })

  it('toggleMark flags a photo, calls the API, and tracks the on-page count', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 2))
    const store = useLibraryStore()
    await store.reload()
    expect(store.markedOnPage).toBe(0)

    await store.toggleMark(1)

    expect(markMock).toHaveBeenCalledWith([1])
    expect(store.photos.find((p) => p.id === 1)!.marked_for_deletion).toBe(true)
    expect(store.markedOnPage).toBe(1)

    await store.toggleMark(1)
    expect(unmarkMock).toHaveBeenCalledWith([1])
    expect(store.markedOnPage).toBe(0)
  })

  it('reverts the optimistic mark if the API call fails', async () => {
    listPhotosMock.mockResolvedValue(page([1], 1))
    const store = useLibraryStore()
    await store.reload()
    markMock.mockRejectedValueOnce(new Error('offline'))

    await store.toggleMark(1)

    expect(store.photos[0]!.marked_for_deletion).toBe(false)
    expect(store.error).toContain('offline')
  })

  it('marking the selection sends every selected id to the API', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2, 3, 4], 4))
    const store = useLibraryStore()
    await store.reload()
    store.clickPhoto(1)
    store.clickPhoto(3, { shift: true, toggle: false })

    await store.setMarkedForSelection(true)

    expect(markMock).toHaveBeenCalledWith([1, 2, 3])
    expect(store.markedOnPage).toBe(3)
    expect(store.photos.find((p) => p.id === 4)!.marked_for_deletion).toBe(false)
  })

  it('unmarking the selection clears the flag on every selected photo', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 2))
    const store = useLibraryStore()
    await store.reload()
    store.clickPhoto(1)
    store.clickPhoto(2, { shift: true, toggle: false })
    await store.setMarkedForSelection(true)

    await store.setMarkedForSelection(false)

    expect(unmarkMock).toHaveBeenCalledWith([1, 2])
    expect(store.markedOnPage).toBe(0)
  })

  it('a failed bulk mark reverts the tiles and surfaces the error', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 2))
    const store = useLibraryStore()
    await store.reload()
    store.clickPhoto(1)
    store.clickPhoto(2, { shift: true, toggle: false })
    markMock.mockRejectedValueOnce(new Error('offline'))

    await store.setMarkedForSelection(true)

    expect(store.photos.every((p) => !p.marked_for_deletion)).toBe(true)
    expect(store.error).toContain('offline')
  })

  it('marking with nothing selected touches neither the API nor the photos', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 2))
    const store = useLibraryStore()
    await store.reload()

    await store.setMarkedForSelection(true)

    expect(markMock).not.toHaveBeenCalled()
    expect(store.markedOnPage).toBe(0)
  })

  it('changing page clears the selection', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 250))
    const store = useLibraryStore()
    await store.reload()
    store.clickPhoto(1)
    expect(store.selectedIds.size).toBe(1)

    await store.nextPage()

    expect(store.selectedIds.size).toBe(0)
  })

  it('reloading after a filter change clears the selection', async () => {
    listPhotosMock.mockResolvedValue(page([1, 2], 2))
    const store = useLibraryStore()
    await store.reload()
    store.clickPhoto(1)
    store.clickPhoto(2, { shift: true, toggle: false })

    await store.setFolder('/lib/Updated')

    expect(store.selectedIds.size).toBe(0)
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
