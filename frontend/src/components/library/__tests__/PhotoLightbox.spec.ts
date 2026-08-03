import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PhotoLightbox from '../PhotoLightbox.vue'
import { useLibraryStore } from '@/stores/library'
import { listSimilarPhotos } from '@/api/photos'
import type { PhotoDetail, PhotoPage, PhotoRead, SimilarPhoto } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  listPhotos: vi.fn<() => Promise<PhotoPage>>(),
  getFacets: vi.fn<() => Promise<unknown>>().mockResolvedValue({ file_types: [], cameras: [] }),
  getPhoto: vi.fn<() => Promise<PhotoDetail>>().mockRejectedValue(new Error('no detail')),
  listSimilarPhotos: vi.fn<() => Promise<SimilarPhoto[]>>().mockResolvedValue([]),
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

  it('shows the thumbnail immediately and defers the full preview until settled', async () => {
    vi.useFakeTimers()
    try {
      const { wrapper } = openAt(1)

      // instantly: thumbnail is the stage background, full preview not yet requested
      const stage = wrapper.find('.image-wrap')
      expect(stage.attributes('style')).toContain('/thumb/1')
      expect(wrapper.find('img.image').exists()).toBe(false)

      // after the debounce, the full preview is rendered
      vi.advanceTimersByTime(200)
      await wrapper.vm.$nextTick()
      expect(wrapper.find('img.image').attributes('src')).toBe('/preview/1')
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not request the full preview while rapidly navigating past images', async () => {
    vi.useFakeTimers()
    try {
      const { store, wrapper } = openAt(1)

      // step through several images faster than the debounce window
      store.lightboxStep(1)
      vi.advanceTimersByTime(50)
      store.lightboxStep(1)
      vi.advanceTimersByTime(50)
      await wrapper.vm.$nextTick()

      // still skimming — no full preview <img> requested yet
      expect(wrapper.find('img.image').exists()).toBe(false)

      // settle: now the current image's preview loads
      vi.advanceTimersByTime(200)
      await wrapper.vm.$nextTick()
      expect(wrapper.find('img.image').attributes('src')).toBe('/preview/3')
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows a location link for a photo that has coordinates', () => {
    const store = useLibraryStore()
    store.photos = [{ ...photo(1), latitude: 44.2697, longitude: -71.3034 }]
    store.total = 1
    store.openLightbox(1)
    const wrapper = mount(PhotoLightbox)

    const link = wrapper.get('.meta-map')
    expect(link.text()).toContain('44.26970° N')
    expect(link.attributes('href')).toContain('openstreetmap.org')
    expect(wrapper.find('iframe').exists()).toBe(false) // nothing loads a map on render
  })

  it('has no location line when the photo has no coordinates', () => {
    const { wrapper } = openAt(1)

    expect(wrapper.find('.meta-map').exists()).toBe(false)
  })

  it('offers visually similar photos once the user settles on one', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(listSimilarPhotos).mockResolvedValue([
        { photo: photo(3), distance: 2, similarity_pct: 97 },
        { photo: photo(42), distance: 5, similarity_pct: 92 }, // not on this page
      ])
      const { wrapper } = openAt(1)

      await vi.advanceTimersByTimeAsync(200)

      const thumbs = wrapper.findAll('.similar-thumb')
      expect(thumbs).toHaveLength(2)
      expect(thumbs[0]!.text()).toContain('97%')
      expect((thumbs[0]!.element as HTMLButtonElement).disabled).toBe(false)
      // The lightbox walks the loaded page, so an off-page match can't be opened.
      expect((thumbs[1]!.element as HTMLButtonElement).disabled).toBe(true)
      expect(thumbs[1]!.attributes('title')).toContain('another page')
    } finally {
      vi.useRealTimers()
    }
  })

  it('clicking a similar photo on this page jumps to it', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(listSimilarPhotos).mockResolvedValue([
        { photo: photo(3), distance: 2, similarity_pct: 97 },
      ])
      const { store, wrapper } = openAt(1)
      await vi.advanceTimersByTimeAsync(200)

      await wrapper.get('.similar-thumb').trigger('click')

      expect(store.lightboxPhoto?.id).toBe(3)
    } finally {
      vi.useRealTimers()
    }
  })

  it('says nothing when a photo has no similar siblings', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(listSimilarPhotos).mockResolvedValue([])
      const { wrapper } = openAt(1)

      await vi.advanceTimersByTimeAsync(200)

      expect(wrapper.find('.similar').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('skimming does not fire a similarity query per frame', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(listSimilarPhotos).mockClear()
      vi.mocked(listSimilarPhotos).mockResolvedValue([])
      const { store } = openAt(1)

      store.lightboxStep(1)
      vi.advanceTimersByTime(50)
      store.lightboxStep(1)
      await vi.advanceTimersByTimeAsync(200)

      expect(vi.mocked(listSimilarPhotos)).toHaveBeenCalledTimes(1)
      expect(vi.mocked(listSimilarPhotos)).toHaveBeenCalledWith(3)
    } finally {
      vi.useRealTimers()
    }
  })
})
