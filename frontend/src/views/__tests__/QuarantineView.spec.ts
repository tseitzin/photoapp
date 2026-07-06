import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import QuarantineView from '../QuarantineView.vue'
import { listMarkedForRemoval } from '@/api/duplicates'
import { quarantinePhotos } from '@/api/files'
import { listPhotos } from '@/api/photos'
import type { PhotoRead } from '@/api/photos'

function photo(id: number, status: PhotoRead['status'] = 'quarantined'): PhotoRead {
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
    status,
    marked_for_deletion: false,
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

describe('QuarantineView quarantine action refreshes the sections', () => {
  const markedMock = vi.mocked(listMarkedForRemoval)
  const listPhotosMock = vi.mocked(listPhotos)
  const quarantineMock = vi.mocked(quarantinePhotos)

  beforeEach(() => {
    setActivePinia(createPinia())
    markedMock.mockReset()
    listPhotosMock.mockReset()
    quarantineMock.mockReset()
  })

  it('moves photos into "In quarantine" without a manual refresh', async () => {
    // initial load: one photo marked for removal, quarantine empty
    markedMock.mockResolvedValueOnce([photo(1, 'active')])
    listPhotosMock.mockResolvedValueOnce({ items: [], total: 0, limit: 1000, offset: 0 })
    quarantineMock.mockResolvedValue({ batch_id: 'b', succeeded: 1, failed: 0, results: [] })
    // reload after quarantining: nothing marked, one quarantined
    markedMock.mockResolvedValueOnce([])
    listPhotosMock.mockResolvedValueOnce({
      items: [photo(1, 'quarantined')],
      total: 1,
      limit: 1000,
      offset: 0,
    })

    const wrapper = await mountLoaded()
    expect(wrapper.text()).toContain('Quarantine 1 photos')
    expect(wrapper.text()).toContain('Quarantine is empty.')

    // click "Quarantine N photos…" then confirm in the dialog
    await wrapper.get('.card .btn--primary').trigger('click')
    await wrapper.get('.backdrop .btn--primary').trigger('click')
    await flushPromises()

    expect(quarantineMock).toHaveBeenCalledWith([1], false)
    expect(wrapper.text()).not.toContain('Quarantine is empty.')
    expect(wrapper.findAll('.row--selectable')).toHaveLength(1)
    expect(wrapper.text()).toContain('Nothing marked')
  })
})
