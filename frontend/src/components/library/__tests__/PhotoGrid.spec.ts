import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PhotoGrid from '../PhotoGrid.vue'
import { useLibraryStore } from '@/stores/library'
import { markPhotos, unmarkPhotos } from '@/api/photos'
import type { PhotoRead } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  markPhotos: vi.fn<() => Promise<unknown>>().mockResolvedValue({ marked: true, affected: 1 }),
  unmarkPhotos: vi.fn<() => Promise<unknown>>().mockResolvedValue({ marked: false, affected: 1 }),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
}))

const markMock = vi.mocked(markPhotos)
const unmarkMock = vi.mocked(unmarkPhotos)

function photo(id: number, marked = false): PhotoRead {
  return {
    id,
    root_id: 1,
    path: `/lib/p${id}.jpg`,
    filename: `p${id}.jpg`,
    ext: 'jpg',
    mime: 'image/jpeg',
    size_bytes: 1000,
    width: 100,
    height: 80,
    captured_at: null,
    camera_make: null,
    camera_model: null,
    status: 'active',
    marked_for_deletion: marked,
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('PhotoGrid interactions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    markMock.mockClear()
    unmarkMock.mockClear()
  })

  it('single click selects the photo without opening the lightbox', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2)]
    const wrapper = mount(PhotoGrid)

    await wrapper.findAll('.tile-img')[0]!.trigger('click')

    expect(store.selectedPhotoId).toBe(1)
    expect(store.lightboxOpen).toBe(false)
    expect(wrapper.emitted('open')).toBeUndefined()
  })

  it('double click selects and emits open for the full-screen lightbox', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2)]
    const wrapper = mount(PhotoGrid)

    await wrapper.findAll('.tile-img')[1]!.trigger('dblclick')

    expect(store.selectedPhotoId).toBe(2)
    expect(wrapper.emitted('open')?.[0]).toEqual([2])
  })

  it('a marked photo shows the marked styling', () => {
    const store = useLibraryStore()
    store.photos = [photo(1, true), photo(2)]
    const wrapper = mount(PhotoGrid)

    const tiles = wrapper.findAll('.tile')
    expect(tiles[0]!.classes()).toContain('tile--marked')
    expect(tiles[1]!.classes()).not.toContain('tile--marked')
  })

  it('clicking the mark toggle flags the photo for deletion', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2)]
    const wrapper = mount(PhotoGrid)

    await wrapper.findAll('.mark-toggle')[0]!.trigger('click')

    expect(markMock).toHaveBeenCalledWith([1])
    expect(store.photos[0]!.marked_for_deletion).toBe(true)
  })

  it('clicking the mark toggle on a marked photo unmarks it', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1, true)]
    const wrapper = mount(PhotoGrid)

    await wrapper.get('.mark-toggle').trigger('click')

    expect(unmarkMock).toHaveBeenCalledWith([1])
    expect(store.photos[0]!.marked_for_deletion).toBe(false)
  })
})
