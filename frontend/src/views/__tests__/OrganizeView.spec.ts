import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import OrganizeView from '../OrganizeView.vue'
import { useLibraryStore } from '@/stores/library'
import { useOrganizeStore } from '@/stores/organize'
import { previewOrganize } from '@/api/organize'
import type { FolderNode } from '@/api/folders'
import type { OrganizePreview, OrganizeRun } from '@/api/organize'

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

function folder(path: string, overrides: Partial<FolderNode> = {}): FolderNode {
  return {
    path,
    name: path.split('/').pop() ?? path,
    parent_path: null,
    depth: 0,
    photo_count: 12,
    direct_count: 12,
    has_children: false,
    root_id: 1,
    ...overrides,
  }
}

function preview(overrides: Partial<OrganizePreview> = {}): OrganizePreview {
  return {
    total: 12,
    planned: 10,
    duplicates_in_set: 2,
    duplicates_skipped: 2,
    already_organized: 0,
    undated: 1,
    est_bytes: 2048,
    example_paths: ['/lib/Organized/2024/07/a.jpg'],
    rename_example: { old: 'IMG_1.jpg', new: '2024-07-15_143022.jpg' },
    destination_new_root: false,
    ...overrides,
  }
}

function mountView() {
  return mount(OrganizeView, {
    global: {
      stubs: { RouterLink: true },
      mocks: { $router: { push: vi.fn<() => Promise<void>>() } },
    },
  })
}

describe('OrganizeView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    previewMock.mockReset()
    previewMock.mockResolvedValue(preview())
  })

  it('shows an empty state with a Library link when nothing is selected', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.empty').exists()).toBe(true)
    expect(wrapper.find('.apply').exists()).toBe(true)
    expect((wrapper.find('.apply').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('renders the working set and preview once folders are checked', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib/inbox')]
    library.toggleChecked('/lib/inbox')
    const organize = useOrganizeStore()
    organize.destination = '/lib/Organized'
    organize.preview = preview()

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.name').text()).toBe('inbox')
    expect(wrapper.find('.big').text()).toBe('10')
    expect(wrapper.text()).toContain('Duplicates skipped')
    expect((wrapper.find('.apply').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('switching the segmented mode updates the help text', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib/inbox')]
    library.toggleChecked('/lib/inbox')
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.help').text()).toContain('keep their current folder names')

    const dateBtn = wrapper
      .findAll('.seg-btn')
      .find((b) => b.text() === 'By date')
    await dateBtn!.trigger('click')

    expect(wrapper.find('.help').text()).toContain('Year / Month')
    expect(wrapper.find('.help').text()).toContain('Undated/')
  })

  it('tells the user when the destination will be added to the library', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib/inbox')]
    library.toggleChecked('/lib/inbox')
    const organize = useOrganizeStore()
    organize.preview = preview({ destination_new_root: true })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.new-root-note').text()).toContain('added automatically')
  })

  it('shows the rename example from the preview', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib/inbox')]
    library.toggleChecked('/lib/inbox')
    const organize = useOrganizeStore()
    organize.preview = preview()

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.rename-old').text()).toBe('IMG_1.jpg')
    expect(wrapper.find('.rename-new').text()).toBe('2024-07-15_143022.jpg')
  })

  it('shows the success banner after a completed run', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib/inbox')]
    const organize = useOrganizeStore()
    organize.phase = 'done'
    organize.activeRun = {
      id: 1,
      status: 'completed',
      params: {
        folders: ['/lib/inbox'],
        destination: '/lib/Organized',
        mode: 'date',
        rename: false,
        skip_duplicates: true,
      },
      batch_id: 'b',
      total: 12,
      planned: 10,
      moved: 10,
      skipped_duplicates: 2,
      already_organized: 0,
      undated: 1,
      failed_count: 0,
      est_bytes: 2048,
      message: null,
      started_at: null,
      finished_at: null,
      created_at: '2026-07-12T00:00:00Z',
    }

    const wrapper = mountView()
    await flushPromises()

    const banner = wrapper.find('.banner')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('Organized 10 photos into')
    expect(banner.text()).toContain('/lib/Organized')
    expect(banner.text()).toContain('2 duplicates skipped')
  })

  it('the destination picker chooses a folder and rejects bad new-folder names', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib', { has_children: false })]
    library.toggleChecked('/lib')
    const organize = useOrganizeStore()
    organize.destination = '/lib'
    organize.pickerOpen = true

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.node').trigger('click')

    // hidden-folder names are rejected
    await wrapper.find('.new-folder').trigger('click')
    await wrapper.find('.new-input').setValue('.hidden')
    await wrapper.find('.choose').trigger('click')
    expect(wrapper.find('.error').text()).toContain('cannot start with')
    expect(organize.pickerOpen).toBe(true)

    // pasted error-message text (colons, trailing spaces) is rejected
    await wrapper
      .find('.new-input')
      .setValue('Destination is outside approved directories: /Volumes/TimDrive/Updated')
    await wrapper.find('.choose').trigger('click')
    expect(wrapper.find('.error').text()).toContain('“:”')
    expect(organize.pickerOpen).toBe(true)

    // a valid segment is appended to the selected folder
    await wrapper.find('.new-input').setValue('Organized')
    await wrapper.find('.choose').trigger('click')
    expect(organize.destination).toBe('/lib/Organized')
    expect(organize.pickerOpen).toBe(false)
  })

  it('the destination picker accepts a typed absolute path', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib', { has_children: false })]
    library.toggleChecked('/lib')
    const organize = useOrganizeStore()
    organize.destination = '/lib'
    organize.pickerOpen = true

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.new-folder').trigger('click')
    await wrapper.find('.new-input').setValue('/Volumes/TimDrive/Updated')
    await wrapper.find('.choose').trigger('click')

    expect(organize.destination).toBe('/Volumes/TimDrive/Updated')
    expect(organize.pickerOpen).toBe(false)
  })

  it('the destination picker accepts a nested relative subpath', async () => {
    const library = useLibraryStore()
    library.folders = [folder('/lib', { has_children: false })]
    library.toggleChecked('/lib')
    const organize = useOrganizeStore()
    organize.destination = '/lib'
    organize.pickerOpen = true

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.node').trigger('click')
    await wrapper.find('.new-folder').trigger('click')
    await wrapper.find('.new-input').setValue('Organized/2024')
    await wrapper.find('.choose').trigger('click')

    expect(organize.destination).toBe('/lib/Organized/2024')
    expect(organize.pickerOpen).toBe(false)
  })
})
