import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ScanView from '../ScanView.vue'
import OrganizeView from '../OrganizeView.vue'
import { getScan, listScans } from '@/api/scans'
import { getOrganizeRun, listOrganizeRuns } from '@/api/organize'
import type { ScanRead } from '@/api/scans'
import type { OrganizeRun } from '@/api/organize'

vi.mock('@/api/scans', () => ({
  startScan: vi.fn<() => Promise<ScanRead>>(),
  getScan: vi.fn<() => Promise<ScanRead>>(),
  listScans: vi.fn<() => Promise<ScanRead[]>>(),
  cancelScan: vi.fn<() => Promise<ScanRead>>(),
  TERMINAL_SCAN_STATUSES: ['completed', 'failed', 'cancelled'],
}))
vi.mock('@/api/scanRoots', () => ({
  listScanRoots: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
  createScanRoot: vi.fn<() => Promise<unknown>>(),
  deleteScanRoot: vi.fn<() => Promise<unknown>>(),
}))
vi.mock('@/api/organize', () => ({
  previewOrganize: vi.fn<() => Promise<unknown>>(),
  startOrganize: vi.fn<() => Promise<OrganizeRun>>(),
  getOrganizeRun: vi.fn<() => Promise<OrganizeRun>>(),
  listOrganizeRuns: vi.fn<() => Promise<OrganizeRun[]>>(),
  TERMINAL_ORGANIZE_STATUSES: ['completed', 'failed'],
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

const runningScan: ScanRead = {
  id: 1,
  status: 'running',
  root_ids: null,
  files_found: 10,
  files_processed: 2,
  files_added: 2,
  files_changed: 0,
  files_unchanged: 0,
  files_missing: 0,
  files_moved: 0,
  error_count: 0,
  current_path: null,
  message: null,
  started_at: null,
  finished_at: null,
  created_at: '2026-08-02T00:00:00Z',
}

const runningRun: OrganizeRun = {
  id: 1,
  status: 'running',
  params: {
    folders: ['/lib/inbox'],
    destination: '/lib/Organized',
    mode: 'date',
    rename: false,
    skip_duplicates: true,
  },
  batch_id: 'b-1',
  total: 10,
  planned: 10,
  moved: 2,
  skipped_duplicates: 0,
  already_organized: 0,
  undated: 0,
  failed_count: 0,
  est_bytes: 100,
  message: null,
  started_at: null,
  finished_at: null,
  created_at: '2026-08-02T00:00:00Z',
}

describe('background polling stops when you leave the view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.mocked(listScans).mockResolvedValue([runningScan])
    vi.mocked(getScan).mockResolvedValue(runningScan)
    vi.mocked(listOrganizeRuns).mockResolvedValue([runningRun])
    vi.mocked(getOrganizeRun).mockResolvedValue(runningRun)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('the scan view stops polling on unmount', async () => {
    const wrapper = mount(ScanView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    expect(vi.mocked(getScan).mock.calls.length).toBeGreaterThan(0)

    wrapper.unmount()
    const afterLeaving = vi.mocked(getScan).mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)

    expect(vi.mocked(getScan).mock.calls.length).toBe(afterLeaving)
  })

  it('the organize view stops polling on unmount', async () => {
    const wrapper = mount(OrganizeView, {
      global: {
        stubs: { RouterLink: true },
        mocks: { $router: { push: vi.fn<() => Promise<void>>() } },
      },
    })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    expect(vi.mocked(getOrganizeRun).mock.calls.length).toBeGreaterThan(0)

    wrapper.unmount()
    const afterLeaving = vi.mocked(getOrganizeRun).mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)

    expect(vi.mocked(getOrganizeRun).mock.calls.length).toBe(afterLeaving)
  })
})
