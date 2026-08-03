import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ScanView from '../ScanView.vue'
import { useScanStore } from '@/stores/scan'
import { listScanErrors } from '@/api/scans'
import { backfillGps } from '@/api/maintenance'
import type { ScanErrorPage, ScanRead } from '@/api/scans'
import type { BackfillResult } from '@/api/maintenance'

vi.mock('@/api/scans', () => ({
  startScan: vi.fn<() => Promise<ScanRead>>(),
  getScan: vi.fn<() => Promise<ScanRead>>(),
  listScans: vi.fn<() => Promise<ScanRead[]>>().mockResolvedValue([]),
  cancelScan: vi.fn<() => Promise<ScanRead>>(),
  listScanErrors: vi.fn<() => Promise<ScanErrorPage>>(),
  TERMINAL_SCAN_STATUSES: ['completed', 'failed', 'cancelled'],
}))
vi.mock('@/api/scanRoots', () => ({
  listScanRoots: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
  createScanRoot: vi.fn<() => Promise<unknown>>(),
  deleteScanRoot: vi.fn<() => Promise<unknown>>(),
}))
vi.mock('@/api/maintenance', () => ({
  backfillGps: vi.fn<() => Promise<BackfillResult>>(),
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
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))

const completedScan: ScanRead = {
  id: 7,
  status: 'completed',
  root_ids: null,
  files_found: 100,
  files_processed: 100,
  files_added: 98,
  files_changed: 0,
  files_unchanged: 0,
  files_missing: 0,
  files_moved: 0,
  error_count: 2,
  current_path: null,
  message: null,
  started_at: null,
  finished_at: null,
  created_at: '2026-08-02T00:00:00Z',
}

function mountView() {
  return mount(ScanView, { global: { stubs: { RouterLink: true } } })
}

describe('ScanView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(listScanErrors).mockReset()
    vi.mocked(backfillGps).mockReset()
  })

  it('a finished scan with failures offers to show them', async () => {
    const store = useScanStore()
    store.phase = 'done'
    store.activeScan = completedScan
    vi.mocked(listScanErrors).mockResolvedValue({
      items: [
        { id: 1, path: '/lib/broken.jpg', error: 'cannot identify image file', created_at: 'x' },
        { id: 2, path: '/lib/locked.jpg', error: 'Permission denied', created_at: 'x' },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('.errors-toggle').trigger('click')
    await flushPromises()

    expect(vi.mocked(listScanErrors)).toHaveBeenCalledWith(7)
    const rows = wrapper.findAll('.errors-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('/lib/broken.jpg')
    expect(rows[0]!.text()).toContain('cannot identify image file')
    expect(rows[1]!.text()).toContain('Permission denied')
  })

  it('a clean scan does not offer an error list', async () => {
    const store = useScanStore()
    store.phase = 'done'
    store.activeScan = { ...completedScan, error_count: 0 }
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.errors-block').exists()).toBe(false)
  })

  it('finding locations reports how many photos gained one', async () => {
    vi.mocked(backfillGps).mockResolvedValue({
      processed: 4106,
      updated: 2340,
      next_after_id: null,
      remaining: 0,
    })
    const wrapper = mountView()
    await flushPromises()

    const button = wrapper
      .findAll('button')
      .find((b) => b.text() === 'Find locations')
    await button!.trigger('click')
    await flushPromises()

    expect(vi.mocked(backfillGps)).toHaveBeenCalled()
    expect(wrapper.text()).toContain('found locations for 2,340')
  })
})
