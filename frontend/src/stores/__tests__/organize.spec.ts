import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useOrganizeStore } from '../organize'
import { useLibraryStore } from '../library'
import { getOrganizeRun, listOrganizeRuns, previewOrganize, startOrganize } from '@/api/organize'
import type { OrganizePreview, OrganizeRun } from '@/api/organize'
import type { FolderNode } from '@/api/folders'

vi.mock('@/api/organize', () => ({
  previewOrganize: vi.fn<() => Promise<OrganizePreview>>(),
  startOrganize: vi.fn<() => Promise<OrganizeRun>>(),
  getOrganizeRun: vi.fn<() => Promise<OrganizeRun>>(),
  listOrganizeRuns: vi.fn<() => Promise<OrganizeRun[]>>().mockResolvedValue([]),
  TERMINAL_ORGANIZE_STATUSES: ['completed', 'failed'],
}))
vi.mock('@/api/photos', () => ({
  listPhotos: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 }),
  getFacets: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ file_types: [], cameras: [] }),
  markPhotos: vi.fn<() => Promise<unknown>>(),
  unmarkPhotos: vi.fn<() => Promise<unknown>>(),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))
vi.mock('@/api/folders', () => ({
  listFolders: vi.fn<() => Promise<never[]>>().mockResolvedValue([]),
}))

const previewMock = vi.mocked(previewOrganize)
const startMock = vi.mocked(startOrganize)
const getRunMock = vi.mocked(getOrganizeRun)
const listRunsMock = vi.mocked(listOrganizeRuns)

function folder(path: string, overrides: Partial<FolderNode> = {}): FolderNode {
  const name = path.split('/').pop() ?? path
  return {
    path,
    name,
    parent_path: path.includes('/') ? path.slice(0, path.lastIndexOf('/')) || null : null,
    depth: 0,
    photo_count: 5,
    direct_count: 5,
    has_children: false,
    root_id: 1,
    ...overrides,
  }
}

function preview(overrides: Partial<OrganizePreview> = {}): OrganizePreview {
  return {
    total: 5,
    planned: 5,
    duplicates_in_set: 0,
    duplicates_skipped: 0,
    already_organized: 0,
    undated: 0,
    est_bytes: 1000,
    example_paths: ['/lib/Organized/2024/07/a.jpg'],
    rename_example: null,
    ...overrides,
  }
}

function run(overrides: Partial<OrganizeRun> = {}): OrganizeRun {
  return {
    id: 3,
    status: 'running',
    params: {
      folders: ['/lib/inbox'],
      destination: '/lib/Organized',
      mode: 'date',
      rename: false,
      skip_duplicates: true,
    },
    batch_id: 'b-1',
    total: 5,
    planned: 5,
    moved: 0,
    skipped_duplicates: 0,
    already_organized: 0,
    undated: 0,
    failed_count: 0,
    est_bytes: 1000,
    message: null,
    started_at: null,
    finished_at: null,
    created_at: '2026-07-12T00:00:00Z',
    ...overrides,
  }
}

function checkFolders(...paths: string[]) {
  const library = useLibraryStore()
  library.folders = paths.map((p) => folder(p))
  for (const p of paths) library.toggleChecked(p)
  return library
}

describe('organize store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    previewMock.mockReset()
    previewMock.mockResolvedValue(preview())
    startMock.mockReset()
    getRunMock.mockReset()
    listRunsMock.mockReset()
    listRunsMock.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('refreshes the preview (debounced) when an input changes', async () => {
    checkFolders('/lib/inbox')
    const store = useOrganizeStore()
    store.destination = '/lib/Organized'

    store.mode = 'date'
    await vi.advanceTimersByTimeAsync(100)
    store.rename = true // changes within the debounce window collapse into one call
    await vi.advanceTimersByTimeAsync(400)

    expect(previewMock).toHaveBeenCalledTimes(1)
    expect(previewMock).toHaveBeenCalledWith({
      folders: ['/lib/inbox'],
      destination: '/lib/Organized',
      mode: 'date',
      rename: true,
      skip_duplicates: true,
    })
    expect(store.preview?.planned).toBe(5)
  })

  it('clears the preview when the working set becomes empty', async () => {
    const library = checkFolders('/lib/inbox')
    const store = useOrganizeStore()
    store.destination = '/lib/Organized'
    await vi.advanceTimersByTimeAsync(400)
    expect(store.preview).not.toBeNull()

    library.uncheckSubtree('/lib/inbox')
    await vi.advanceTimersByTimeAsync(400)

    expect(store.preview).toBeNull()
  })

  it('apply starts a run, polls to completion and refreshes the library', async () => {
    checkFolders('/lib/inbox')
    const store = useOrganizeStore()
    store.destination = '/lib/Organized'
    startMock.mockResolvedValue(run({ status: 'pending' }))
    getRunMock.mockResolvedValueOnce(run({ status: 'running', moved: 3 }))
    getRunMock.mockResolvedValueOnce(run({ status: 'completed', moved: 5 }))

    await store.apply()
    expect(store.phase).toBe('running')

    await vi.advanceTimersByTimeAsync(1000)
    expect(store.progressPct).toBe(60)

    await vi.advanceTimersByTimeAsync(1000)
    expect(store.phase).toBe('done')
    expect(store.activeRun?.moved).toBe(5)

    // polling stopped: no further requests on later ticks
    const calls = getRunMock.mock.calls.length
    await vi.advanceTimersByTimeAsync(3000)
    expect(getRunMock.mock.calls.length).toBe(calls)
  })

  it('a failed run surfaces its message and returns to setup', async () => {
    checkFolders('/lib/inbox')
    const store = useOrganizeStore()
    store.destination = '/lib/Organized'
    startMock.mockResolvedValue(run({ status: 'pending' }))
    getRunMock.mockResolvedValue(run({ status: 'failed', message: 'disk full' }))

    await store.apply()
    await vi.advanceTimersByTimeAsync(1000)

    expect(store.phase).toBe('setup')
    expect(store.error).toBe('disk full')
  })

  it('load resumes polling an active run after navigating away and back', async () => {
    checkFolders('/lib/inbox')
    listRunsMock.mockResolvedValue([run({ status: 'running', moved: 2 })])
    const store = useOrganizeStore()

    await store.load()

    expect(store.phase).toBe('running')
    getRunMock.mockResolvedValue(run({ status: 'completed', moved: 5 }))
    await vi.advanceTimersByTimeAsync(1000)
    expect(store.phase).toBe('done')
  })

  it('load derives a default destination from the first root folder', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib', { depth: 0, has_children: true })]
    const store = useOrganizeStore()

    await store.load()

    expect(store.destination).toBe('/lib/Organized')
  })

  it('removing a working-set folder unchecks its whole subtree in the library', () => {
    const library = useLibraryStore()
    library.folders = [
      folder('/lib/inbox', { depth: 1, has_children: true }),
      folder('/lib/inbox/2024', { depth: 2 }),
    ]
    library.toggleChecked('/lib/inbox')
    library.toggleChecked('/lib/inbox/2024')
    const store = useOrganizeStore()

    store.removeFolder('/lib/inbox')

    expect(library.checkedFolders.size).toBe(0)
    expect(store.workingSet).toEqual([])
  })
})
