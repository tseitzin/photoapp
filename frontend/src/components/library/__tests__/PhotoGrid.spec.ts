import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PhotoGrid from '../PhotoGrid.vue'
import { useLibraryStore } from '@/stores/library'
import type { PhotoRead } from '@/api/photos'

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
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('PhotoGrid interactions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('single click selects the photo without opening the lightbox', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2)]
    const wrapper = mount(PhotoGrid)

    await wrapper.findAll('.tile')[0]!.trigger('click')

    expect(store.selectedPhotoId).toBe(1)
    expect(store.lightboxOpen).toBe(false)
    expect(wrapper.emitted('open')).toBeUndefined()
  })

  it('double click selects and emits open for the full-screen lightbox', async () => {
    const store = useLibraryStore()
    store.photos = [photo(1), photo(2)]
    const wrapper = mount(PhotoGrid)

    await wrapper.findAll('.tile')[1]!.trigger('dblclick')

    expect(store.selectedPhotoId).toBe(2)
    expect(wrapper.emitted('open')?.[0]).toEqual([2])
  })
})
