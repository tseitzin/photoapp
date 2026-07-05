import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import QuarantineView from '../QuarantineView.vue'
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
    status: 'quarantined',
    created_at: '2026-01-01T00:00:00Z',
  }
}

vi.mock('@/api/files', () => ({
  listFileOperations: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 }),
  quarantinePhotos: vi.fn<() => Promise<unknown>>(),
  restorePhotos: vi.fn<() => Promise<unknown>>(),
  deletePhotosPermanently: vi.fn<() => Promise<unknown>>(),
}))
vi.mock('@/api/duplicates', () => ({
  listMarkedForRemoval: vi.fn<() => Promise<PhotoRead[]>>().mockResolvedValue([]),
}))
vi.mock('@/api/photos', () => ({
  listPhotos: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ items: [photo(1), photo(2), photo(3)], total: 3, limit: 1000, offset: 0 }),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
}))

async function mountLoaded() {
  const wrapper = mount(QuarantineView, {
    global: { stubs: { RouterLink: true } },
  })
  await flushPromises()
  return wrapper
}

function rowChecks(wrapper: Awaited<ReturnType<typeof mountLoaded>>) {
  return wrapper.findAll('.row--selectable .row-check')
}

describe('QuarantineView select all', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders one row per quarantined photo', async () => {
    const wrapper = await mountLoaded()
    expect(rowChecks(wrapper)).toHaveLength(3)
  })

  it('select all checks every row and enables the actions', async () => {
    const wrapper = await mountLoaded()

    await wrapper.get('input[aria-label="Select all quarantined photos"]').setValue(true)

    for (const check of rowChecks(wrapper)) {
      expect((check.element as HTMLInputElement).checked).toBe(true)
    }
    const restore = wrapper.findAll('button').find((b) => b.text().startsWith('Restore selected'))
    expect(restore?.text()).toContain('(3)')
    expect(restore?.attributes('disabled')).toBeUndefined()
  })

  it('toggling select all a second time clears the selection', async () => {
    const wrapper = await mountLoaded()
    const selectAll = wrapper.get('input[aria-label="Select all quarantined photos"]')

    await selectAll.setValue(true)
    await selectAll.setValue(false)

    for (const check of rowChecks(wrapper)) {
      expect((check.element as HTMLInputElement).checked).toBe(false)
    }
    const restore = wrapper.findAll('button').find((b) => b.text().startsWith('Restore selected'))
    expect(restore?.attributes('disabled')).toBeDefined()
  })
})
