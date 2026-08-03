import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SelectionBar from '../SelectionBar.vue'
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

/** A store with photos 1–3 loaded and the first two selected. */
function withSelection() {
  const store = useLibraryStore()
  store.photos = [photo(1), photo(2), photo(3)]
  store.clickPhoto(1)
  store.clickPhoto(2, { shift: true, toggle: false })
  return store
}

describe('SelectionBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    markMock.mockClear()
    markMock.mockResolvedValue({ marked: true, affected: 1 })
    unmarkMock.mockClear()
  })

  it('stays hidden until something is selected', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1)]
    const wrapper = mount(SelectionBar)

    expect(wrapper.find('.selection-bar').exists()).toBe(false)

    store.clickPhoto(1)
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.selection-bar').exists()).toBe(true)
  })

  it('reads the number of selected photos', () => {
    withSelection()
    const wrapper = mount(SelectionBar)

    expect(wrapper.get('.count').text()).toBe('2 selected')
  })

  it('marking sends every selected photo to the API', async () => {
    const store = withSelection()
    const wrapper = mount(SelectionBar)

    await wrapper.get('.btn--danger').trigger('click')

    expect(markMock).toHaveBeenCalledWith([1, 2])
    expect(store.markedOnPage).toBe(2)
  })

  it('unmarking clears the flag on the selected photos', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1, true), photo(2, true)]
    store.clickPhoto(1)
    store.clickPhoto(2, { shift: true, toggle: false })
    const wrapper = mount(SelectionBar)

    await wrapper.findAll('.btn')[1]!.trigger('click')

    expect(unmarkMock).toHaveBeenCalledWith([1, 2])
    expect(store.markedOnPage).toBe(0)
  })

  it('clear empties the selection and hides the bar', async () => {
    const store = withSelection()
    const wrapper = mount(SelectionBar)

    await wrapper.get('.clear').trigger('click')

    expect(store.selectedIds.size).toBe(0)
    expect(wrapper.find('.selection-bar').exists()).toBe(false)
  })

  it('escape clears the selection', async () => {
    const store = withSelection()
    const wrapper = mount(SelectionBar)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()

    expect(store.selectedIds.size).toBe(0)
  })

  it('disables its buttons while a bulk mark is in flight', async () => {
    const store = withSelection()
    let release = (): void => {}
    markMock.mockImplementationOnce(
      () => new Promise((resolve) => (release = () => resolve({ marked: true, affected: 2 }))),
    )
    const wrapper = mount(SelectionBar)

    const run = store.setMarkedForSelection(true)
    await wrapper.vm.$nextTick()
    expect(
      wrapper.findAll('.btn').every((b) => (b.element as HTMLButtonElement).disabled),
    ).toBe(true)

    release()
    await run
    await wrapper.vm.$nextTick()
    expect(
      wrapper.findAll('.btn').some((b) => (b.element as HTMLButtonElement).disabled),
    ).toBe(false)
  })

  it('escape leaves the selection alone while the lightbox is open', async () => {
    const store = withSelection()
    store.openLightbox(1)
    const wrapper = mount(SelectionBar)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()

    expect(store.selectedIds.size).toBe(2)
  })
})
