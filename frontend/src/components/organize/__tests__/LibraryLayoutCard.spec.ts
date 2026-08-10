import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LibraryLayoutCard from '../LibraryLayoutCard.vue'
import { useOrganizeStore } from '@/stores/organize'
import type { LibraryLocation } from '@/api/organize'

vi.mock('@/api/organize', () => ({
  previewOrganize: vi.fn<() => Promise<unknown>>(),
  startOrganize: vi.fn<() => Promise<unknown>>(),
  getOrganizeRun: vi.fn<() => Promise<unknown>>(),
  listOrganizeRuns: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
  getLibraryLayout: vi.fn<() => Promise<unknown>>(),
  TERMINAL_ORGANIZE_STATUSES: ['completed', 'failed'],
}))
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))
vi.mock('@/api/photos', () => ({
  listPhotos: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 }),
  getFacets: vi.fn<() => Promise<unknown>>().mockResolvedValue({ file_types: [], cameras: [] }),
  markPhotos: vi.fn<() => Promise<unknown>>(),
  unmarkPhotos: vi.fn<() => Promise<unknown>>(),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))

function cardShowing(locations: LibraryLocation[]) {
  const store = useOrganizeStore()
  store.locations = locations
  return mount(LibraryLayoutCard)
}

describe('LibraryLayoutCard', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('lists each place the library lives, with its count', () => {
    const wrapper = cardShowing([
      { path: '/lib/Camera Roll/Organized', photos: 4949 },
      { path: '/lib/Updated', photos: 984 },
    ])

    const rows = wrapper.findAll('.row').map((row) => [
      row.get('.path').text(),
      row.get('.count').text(),
    ])
    // Short paths are shown whole; only deep ones get elided.
    expect(rows).toEqual([
      ['/lib/Camera Roll/Organized', '4,949'],
      ['/lib/Updated', '984'],
    ])
  })

  it('says plainly when the library is in more than one place', () => {
    const wrapper = cardShowing([
      { path: '/lib/a', photos: 2 },
      { path: '/lib/b', photos: 1 },
    ])

    expect(wrapper.get('.note').text()).toContain('2 places')
  })

  it('stays quiet when the library is all in one place', () => {
    const wrapper = cardShowing([{ path: '/lib/Photos', photos: 5938 }])

    expect(wrapper.find('.note').exists()).toBe(false)
    expect(wrapper.findAll('.row')).toHaveLength(1)
  })

  it('renders nothing at all for an empty library', () => {
    const wrapper = cardShowing([])

    expect(wrapper.find('.card').exists()).toBe(false)
  })

  it('keeps the full path available even when the display is shortened', () => {
    const wrapper = cardShowing([
      { path: '/Volumes/TimDrive/Everything/Dropbox/Photos/Tim/Camera Roll/Organized', photos: 1 },
    ])

    const path = wrapper.get('.path')
    expect(path.text()).toBe('…/Tim/Camera Roll/Organized')
    expect(path.attributes('title')).toBe(
      '/Volumes/TimDrive/Everything/Dropbox/Photos/Tim/Camera Roll/Organized',
    )
  })
})
