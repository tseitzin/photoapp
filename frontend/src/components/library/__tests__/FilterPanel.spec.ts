import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FilterPanel from '../FilterPanel.vue'
import { useLibraryStore } from '@/stores/library'
import type { PhotoRead } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  listPhotos: vi.fn<() => Promise<unknown>>(),
  getFacets: vi.fn<() => Promise<unknown>>().mockResolvedValue({ file_types: [], cameras: [] }),
  markPhotos: vi.fn<() => Promise<unknown>>(),
  unmarkPhotos: vi.fn<() => Promise<unknown>>(),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))

function photo(overrides: Partial<PhotoRead> = {}): PhotoRead {
  return {
    id: 1,
    root_id: 1,
    path: '/lib/trip/p1.jpg',
    filename: 'p1.jpg',
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
    ...overrides,
  }
}

function panelShowing(p: PhotoRead) {
  const store = useLibraryStore()
  store.photos = [p]
  store.selectPhoto(p.id)
  return mount(FilterPanel)
}

describe('FilterPanel location row', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('shows the coordinates of a photo that has them', () => {
    const wrapper = panelShowing(photo({ latitude: 44.2697, longitude: -71.3034 }))

    expect(wrapper.get('.coords').text()).toBe('44.26970° N, 71.30340° W')
  })

  it('offers a map link that opens in a new tab and leaks nothing until clicked', () => {
    const wrapper = panelShowing(photo({ latitude: 44.2697, longitude: -71.3034 }))

    const link = wrapper.get('.map-link')
    expect(link.attributes('href')).toContain('openstreetmap.org')
    expect(link.attributes('href')).toContain('mlat=44.2697')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
    // No embedded map: nothing requests a third-party resource on render.
    expect(wrapper.find('iframe').exists()).toBe(false)
  })

  it('renders southern and western coordinates with the right hemisphere', () => {
    const wrapper = panelShowing(photo({ latitude: -33.8688, longitude: 151.2093 }))

    expect(wrapper.get('.coords').text()).toBe('33.86880° S, 151.20930° E')
  })

  it('names the place above the coordinates', () => {
    const wrapper = panelShowing(
      photo({
        latitude: 42.3601,
        longitude: -71.0589,
        city: 'Boston',
        region: 'Massachusetts',
        country: 'US',
        place_distance_km: 0.2,
      }),
    )

    expect(wrapper.get('.place').text()).toBe('Boston, Massachusetts')
    expect(wrapper.get('.coords').text()).toBe('42.36010° N, 71.05890° W')
  })

  it('says "near" when the nearest known town is far from the photo', () => {
    const wrapper = panelShowing(
      photo({
        latitude: 44.2705,
        longitude: -71.3033,
        city: 'Gorham',
        region: 'New Hampshire',
        country: 'US',
        place_distance_km: 16.7,
      }),
    )

    expect(wrapper.get('.place').text()).toBe('near Gorham, New Hampshire')
  })

  it('still shows coordinates when no place could be named', () => {
    const wrapper = panelShowing(photo({ latitude: 35.0, longitude: -40.0 }))

    expect(wrapper.find('.place').exists()).toBe(false)
    expect(wrapper.get('.coords').text()).toBe('35.00000° N, 40.00000° W')
  })

  it('omits the row entirely for a photo with no coordinates', () => {
    const wrapper = panelShowing(photo())

    expect(wrapper.find('.coords').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Location')
  })
})
