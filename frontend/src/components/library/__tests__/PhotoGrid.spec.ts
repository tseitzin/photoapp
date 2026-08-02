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

function photo(id: number, marked = false, folder = '/lib'): PhotoRead {
  return {
    id,
    root_id: 1,
    path: `${folder}/p${id}.jpg`,
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

/** Selected ids in a stable order, for readable assertions. */
function selection(store: ReturnType<typeof useLibraryStore>): number[] {
  return [...store.selectedIds].sort((a, b) => a - b)
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
    expect(selection(store)).toEqual([1])
    expect(store.lightboxOpen).toBe(false)
    expect(wrapper.emitted('open')).toBeUndefined()
  })

  it('shift+clicking a second photo selects the whole run between them', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2), photo(3), photo(4), photo(5)]
    const wrapper = mount(PhotoGrid)
    const tiles = wrapper.findAll('.tile-img')

    await tiles[1]!.trigger('click')
    await tiles[3]!.trigger('click', { shiftKey: true })

    expect(selection(store)).toEqual([2, 3, 4])
  })

  it('shift+clicking backwards selects the same run', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2), photo(3), photo(4)]
    const wrapper = mount(PhotoGrid)
    const tiles = wrapper.findAll('.tile-img')

    await tiles[3]!.trigger('click')
    await tiles[1]!.trigger('click', { shiftKey: true })

    expect(selection(store)).toEqual([2, 3, 4])
  })

  it('a shift+range spans section headers', async () => {
    const store = useLibraryStore()
    store.photos = [
      photo(1, false, '/lib/trip'),
      photo(2, false, '/lib/trip'),
      photo(3, false, '/lib/home'),
      photo(4, false, '/lib/home'),
    ]
    const wrapper = mount(PhotoGrid)
    expect(wrapper.findAll('.section')).toHaveLength(2)
    const tiles = wrapper.findAll('.tile-img')

    await tiles[1]!.trigger('click')
    await tiles[2]!.trigger('click', { shiftKey: true })

    expect(selection(store)).toEqual([2, 3])
  })

  it('shift+click with nothing selected yet just selects that photo', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2), photo(3)]
    const wrapper = mount(PhotoGrid)

    await wrapper.findAll('.tile-img')[2]!.trigger('click', { shiftKey: true })

    expect(selection(store)).toEqual([3])
  })

  it('cmd+click adds a non-adjacent photo without disturbing the rest', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2), photo(3), photo(4)]
    const wrapper = mount(PhotoGrid)
    const tiles = wrapper.findAll('.tile-img')

    await tiles[0]!.trigger('click')
    await tiles[1]!.trigger('click', { shiftKey: true })
    await tiles[3]!.trigger('click', { metaKey: true })

    expect(selection(store)).toEqual([1, 2, 4])
  })

  it('cmd+click on an already-selected photo removes just that one', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2), photo(3)]
    const wrapper = mount(PhotoGrid)
    const tiles = wrapper.findAll('.tile-img')

    await tiles[0]!.trigger('click')
    await tiles[2]!.trigger('click', { shiftKey: true })
    await tiles[1]!.trigger('click', { ctrlKey: true })

    expect(selection(store)).toEqual([1, 3])
  })

  it('a plain click after a range collapses the selection back to one photo', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2), photo(3)]
    const wrapper = mount(PhotoGrid)
    const tiles = wrapper.findAll('.tile-img')

    await tiles[0]!.trigger('click')
    await tiles[2]!.trigger('click', { shiftKey: true })
    await tiles[1]!.trigger('click')

    expect(selection(store)).toEqual([2])
  })

  it('a selected photo shows the selection badge even when it is marked', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1, true), photo(2)]
    const wrapper = mount(PhotoGrid)

    await wrapper.findAll('.tile-img')[0]!.trigger('click')

    const tiles = wrapper.findAll('.tile')
    expect(tiles[0]!.classes()).toContain('tile--marked')
    expect(tiles[0]!.find('.select-badge').exists()).toBe(true)
    expect(tiles[1]!.find('.select-badge').exists()).toBe(false)
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
