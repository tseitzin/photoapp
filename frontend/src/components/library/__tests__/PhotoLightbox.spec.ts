import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PhotoLightbox from '../PhotoLightbox.vue'
import { useLibraryStore } from '@/stores/library'
import type { PhotoDetail, PhotoPage, PhotoRead } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  listPhotos: vi.fn<() => Promise<PhotoPage>>(),
  getFacets: vi.fn<() => Promise<unknown>>().mockResolvedValue({ file_types: [], cameras: [] }),
  getPhoto: vi.fn<() => Promise<PhotoDetail>>().mockRejectedValue(new Error('no detail')),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))

function photo(id: number): PhotoRead {
  return {
    id,
    root_id: 1,
    path: `/lib/p${id}.jpg`,
    filename: `p${id}.jpg`,
    ext: 'jpg',
    mime: 'image/jpeg',
    size_bytes: 5000,
    width: 100,
    height: 80,
    captured_at: null,
    camera_make: null,
    camera_model: null,
    status: 'active',
    marked_for_deletion: false,
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('PhotoLightbox', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  function openAt(id: number) {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2), photo(3)]
    store.total = 3
    store.openLightbox(id)
    const wrapper = mount(PhotoLightbox)
    return { store, wrapper }
  }

  it('shows the current photo with its position counter', () => {
    const { wrapper } = openAt(2)

    expect(wrapper.find('.filename').text()).toBe('p2.jpg')
    expect(wrapper.find('.counter').text()).toContain('2 / 3')
  })

  it('arrow keys navigate between photos', async () => {
    const { store, wrapper } = openAt(1)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    await wrapper.vm.$nextTick()
    expect(store.lightboxPhoto?.id).toBe(2)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    await wrapper.vm.$nextTick()
    expect(store.lightboxPhoto?.id).toBe(1)
  })

  it('does not step past either end', () => {
    const { store } = openAt(3)

    store.lightboxStep(1)
    expect(store.lightboxIndex).toBe(2)

    store.lightboxIndex = 0
    store.lightboxStep(-1)
    expect(store.lightboxIndex).toBe(0)
  })

  it('escape closes the lightbox', async () => {
    const { store, wrapper } = openAt(1)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()

    expect(store.lightboxOpen).toBe(false)
  })

  it('clicking a filmstrip thumbnail jumps to that photo', async () => {
    const { store, wrapper } = openAt(1)

    const thumbs = wrapper.findAll('.strip-thumb')
    expect(thumbs).toHaveLength(3)
    await thumbs[2]!.trigger('click')

    expect(store.lightboxPhoto?.id).toBe(3)
  })
})
