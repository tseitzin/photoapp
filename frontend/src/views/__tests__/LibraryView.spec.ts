import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LibraryView from '../LibraryView.vue'
import { useLibraryStore } from '@/stores/library'
import { listPhotos } from '@/api/photos'
import type { PhotoPage, PhotoRead } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  listPhotos: vi.fn<() => Promise<PhotoPage>>(),
  getFacets: vi.fn<() => Promise<unknown>>().mockResolvedValue({ file_types: [], cameras: [] }),
  getPhoto: vi.fn<() => Promise<unknown>>().mockRejectedValue(new Error('no detail')),
  markPhotos: vi.fn<() => Promise<unknown>>(),
  unmarkPhotos: vi.fn<() => Promise<unknown>>(),
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
    size_bytes: 1000,
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

function mountView() {
  return mount(LibraryView, { global: { stubs: { RouterLink: true } } })
}

describe('LibraryView error reporting', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(listPhotos).mockResolvedValue({ items: [photo(1)], total: 1, limit: 100, offset: 0 })
  })

  it('shows a failure that happens while the grid is loaded', async () => {
    // The full-pane error state only renders on an empty grid, so before this
    // a failed bulk mark had nowhere to appear and went silent.
    const store = useLibraryStore()
    await store.reload()
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.error-strip').exists()).toBe(false)

    store.error = 'Marked 500 of 600 photos — 100 failed: offline'
    await wrapper.vm.$nextTick()

    const strip = wrapper.get('.error-strip')
    expect(strip.text()).toContain('500 of 600')
    expect(strip.attributes('role')).toBe('alert')
  })

  it('the failure can be dismissed', async () => {
    const store = useLibraryStore()
    await store.reload()
    const wrapper = mountView()
    await flushPromises()
    store.error = 'offline'
    await wrapper.vm.$nextTick()

    await wrapper.get('.error-dismiss').trigger('click')

    expect(store.error).toBeNull()
    expect(wrapper.find('.error-strip').exists()).toBe(false)
  })

  it('an empty grid still uses the full-pane error state, not the strip', async () => {
    vi.mocked(listPhotos).mockRejectedValue(new Error('ECONNREFUSED'))
    const store = useLibraryStore()
    await store.reload()

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.error-strip').exists()).toBe(false)
    expect(wrapper.find('.state--error').exists()).toBe(true)
  })
})
