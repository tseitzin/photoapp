import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ORGANIZE_PREFS_KEY, useOrganizeStore } from '../organize'
import { useLibraryStore } from '../library'
import {
  getLibraryLayout,
  getOrganizeRun,
  listOrganizeRuns,
  previewOrganize,
  startOrganize,
} from '@/api/organize'
import type { LibraryLayout, OrganizePreview, OrganizeRun } from '@/api/organize'
import type { FolderNode } from '@/api/folders'

vi.mock('@/api/organize', () => ({
  previewOrganize: vi.fn<() => Promise<OrganizePreview>>(),
  startOrganize: vi.fn<() => Promise<OrganizeRun>>(),
  getOrganizeRun: vi.fn<() => Promise<OrganizeRun>>(),
  listOrganizeRuns: vi.fn<() => Promise<OrganizeRun[]>>().mockResolvedValue([]),
  getLibraryLayout: vi
    .fn<() => Promise<LibraryLayout>>()
    .mockResolvedValue({ locations: [], total: 0 }),
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
const layoutMock = vi.mocked(getLibraryLayout)

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
    destination_new_root: false,
    destination_inside_source: false,
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
    localStorage.clear()
    setActivePinia(createPinia())
    vi.useFakeTimers()
    previewMock.mockReset()
    previewMock.mockResolvedValue(preview())
    startMock.mockReset()
    getRunMock.mockReset()
    listRunsMock.mockReset()
    listRunsMock.mockResolvedValue([])
    layoutMock.mockReset()
    layoutMock.mockResolvedValue({ locations: [], total: 0 })
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

  it('remembers the destination and mode for the next visit', async () => {
    checkFolders('/lib/inbox')
    const first = useOrganizeStore()
    first.destination = '/lib/Updated'
    first.mode = 'date'
    await vi.advanceTimersByTimeAsync(400)

    // A fresh app session (new pinia, same storage) restores the choice.
    setActivePinia(createPinia())
    const next = useOrganizeStore()

    expect(next.destination).toBe('/lib/Updated')
    expect(next.mode).toBe('date')
  })

  it('falls back to defaults when stored preferences are corrupt', () => {
    localStorage.setItem(ORGANIZE_PREFS_KEY, '{not json')

    const store = useOrganizeStore()

    expect(store.destination).toBe('')
    expect(store.mode).toBe('keep')
    expect(store.skipDuplicates).toBe(true)
  })

  it('discarding the working set keeps the remembered destination', async () => {
    checkFolders('/lib/inbox')
    const store = useOrganizeStore()
    store.destination = '/lib/Updated'
    store.mode = 'date'
    await vi.advanceTimersByTimeAsync(400)

    store.discard()

    expect(store.destination).toBe('/lib/Updated')
    expect(store.mode).toBe('date')
    expect(store.workingSet).toEqual([])
  })

  it('first run prefers an existing Organized root over whichever sorts first', async () => {
    const library = useLibraryStore()
    library.folders = [
      folder('/lib/Archive', { depth: 0 }),
      folder('/lib/Organized', { depth: 0 }),
    ]
    const store = useOrganizeStore()

    await store.load()

    expect(store.destination).toBe('/lib/Organized')
  })

  it('warns when the destination is not where the library already lives', async () => {
    // The real misfire: photos already organized under one folder, a run sent
    // to another, and nothing said so until you browsed the tree afterwards.
    layoutMock.mockResolvedValue({
      locations: [{ path: '/lib/Camera Roll/Organized', photos: 4949 }],
      total: 4949,
    })
    const store = useOrganizeStore()
    await store.load()

    store.destination = '/lib/Updated'

    expect(store.wouldSplitLibrary).toBe(true)
    expect(store.dominantLocation?.photos).toBe(4949)
  })

  it('does not warn when organizing into the place the library already is', async () => {
    layoutMock.mockResolvedValue({
      locations: [{ path: '/lib/Photos', photos: 5938 }],
      total: 5938,
    })
    const store = useOrganizeStore()
    await store.load()

    store.destination = '/lib/Photos'

    expect(store.wouldSplitLibrary).toBe(false)
  })

  it('ignores a trailing slash rather than crying split over it', async () => {
    layoutMock.mockResolvedValue({
      locations: [{ path: '/lib/Photos', photos: 10 }],
      total: 10,
    })
    const store = useOrganizeStore()
    await store.load()

    store.destination = '/lib/Photos/'

    expect(store.wouldSplitLibrary).toBe(false)
  })

  it('does not warn when the library is empty', async () => {
    const store = useOrganizeStore()
    await store.load()

    store.destination = '/lib/anywhere'

    expect(store.wouldSplitLibrary).toBe(false)
  })

  it('offers to point the destination at the existing location', async () => {
    layoutMock.mockResolvedValue({
      locations: [
        { path: '/lib/Camera Roll/Organized', photos: 4949 },
        { path: '/lib/Updated', photos: 984 },
      ],
      total: 5933,
    })
    const store = useOrganizeStore()
    await store.load()
    store.destination = '/lib/Elsewhere'

    store.useDominantLocation()

    expect(store.destination).toBe('/lib/Camera Roll/Organized')
    expect(store.wouldSplitLibrary).toBe(false)
  })

  it('a first-run destination defaults to where the library already lives', async () => {
    layoutMock.mockResolvedValue({
      locations: [{ path: '/lib/Photos', photos: 5938 }],
      total: 5938,
    })
    const store = useOrganizeStore()

    await store.load()

    expect(store.destination).toBe('/lib/Photos')
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
