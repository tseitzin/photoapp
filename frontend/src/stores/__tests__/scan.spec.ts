import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useScanStore } from '../scan'
import { getScan, startScan } from '@/api/scans'
import type { ScanRead } from '@/api/scans'

vi.mock('@/api/scans', () => ({
  startScan: vi.fn<() => Promise<ScanRead>>(),
  getScan: vi.fn<() => Promise<ScanRead>>(),
  listScans: vi.fn<() => Promise<ScanRead[]>>().mockResolvedValue([]),
  cancelScan: vi.fn<() => Promise<ScanRead>>(),
  TERMINAL_SCAN_STATUSES: ['completed', 'failed', 'cancelled'],
}))
vi.mock('@/api/scanRoots', () => ({
  listScanRoots: vi
    .fn<() => Promise<unknown[]>>()
    .mockResolvedValue([{ id: 1, path: '/lib', enabled: true, created_at: '' }]),
  createScanRoot: vi.fn<() => Promise<unknown>>(),
  deleteScanRoot: vi.fn<() => Promise<void>>(),
}))

const startScanMock = vi.mocked(startScan)
const getScanMock = vi.mocked(getScan)

function scan(overrides: Partial<ScanRead>): ScanRead {
  return {
    id: 7,
    status: 'running',
    root_ids: null,
    files_found: 0,
    files_processed: 0,
    files_added: 0,
    files_changed: 0,
    files_unchanged: 0,
    files_missing: 0,
    files_moved: 0,
    error_count: 0,
    current_path: null,
    message: null,
    started_at: null,
    finished_at: null,
    created_at: '2026-07-03T00:00:00Z',
    ...overrides,
  }
}

describe('scan store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    startScanMock.mockReset()
    getScanMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starting a scan enters the scanning phase and polls progress', async () => {
    startScanMock.mockResolvedValue(scan({ status: 'pending' }))
    getScanMock.mockResolvedValue(
      scan({ status: 'running', files_found: 100, files_processed: 40, current_path: '/lib/x' }),
    )
    const store = useScanStore()

    await store.start()
    expect(store.phase).toBe('scanning')

    await vi.advanceTimersByTimeAsync(1000)

    expect(store.activeScan?.files_processed).toBe(40)
    expect(store.progressPct).toBe(40)
    expect(store.activeScan?.current_path).toBe('/lib/x')
  })

  it('moves to done and stops polling when the scan completes', async () => {
    startScanMock.mockResolvedValue(scan({ status: 'pending' }))
    getScanMock.mockResolvedValue(scan({ status: 'completed', files_found: 5 }))
    const store = useScanStore()
    await store.start()

    await vi.advanceTimersByTimeAsync(1000)
    expect(store.phase).toBe('done')

    await vi.advanceTimersByTimeAsync(3000)
    expect(getScanMock).toHaveBeenCalledTimes(1)
  })

  it('returns to setup with the failure message when a scan fails', async () => {
    startScanMock.mockResolvedValue(scan({ status: 'pending' }))
    getScanMock.mockResolvedValue(scan({ status: 'failed', message: 'disk exploded' }))
    const store = useScanStore()
    await store.start()

    await vi.advanceTimersByTimeAsync(1000)

    expect(store.phase).toBe('setup')
    expect(store.error).toBe('disk exploded')
  })

  it('surfaces a start rejection (e.g. scan already running) as an error', async () => {
    startScanMock.mockRejectedValue(new Error('A scan is already in progress'))
    const store = useScanStore()

    await store.start()

    expect(store.phase).toBe('setup')
    expect(store.error).toContain('already in progress')
  })
})
