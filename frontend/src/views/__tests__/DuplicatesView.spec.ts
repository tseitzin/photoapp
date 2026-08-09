import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory, type Router } from 'vue-router'
import DuplicatesView from '../DuplicatesView.vue'
import { getDuplicateSummary, listGroups } from '@/api/duplicates'
import type { DuplicateGroup, DuplicateGroupPage, DuplicateSummary } from '@/api/duplicates'
import type { PhotoRead } from '@/api/photos'

function summary(overrides: Partial<DuplicateSummary> = {}): DuplicateSummary {
  return {
    groups: 3,
    pending_groups: 1,
    reviewed_groups: 15,
    dismissed_groups: 2,
    exact_groups: 3,
    similar_groups: 0,
    member_photos: 6,
    marked_remove_count: 0,
    marked_remove_bytes: 0,
    ...overrides,
  }
}

vi.mock('@/api/duplicates', () => ({
  listGroups: vi.fn<() => Promise<DuplicateGroupPage>>(),
  decideGroup: vi.fn<() => Promise<unknown>>(),
  dismissGroup: vi.fn<() => Promise<unknown>>(),
  reopenGroup: vi.fn<() => Promise<unknown>>(),
  getDuplicateSummary: vi.fn<() => Promise<DuplicateSummary>>(),
}))
vi.mock('@/api/photos', () => ({
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))

const listGroupsMock = vi.mocked(listGroups)
const summaryMock = vi.mocked(getDuplicateSummary)

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
    height: 100,
    captured_at: null,
    camera_make: null,
    camera_model: null,
    status: 'active',
    marked_for_deletion: false,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function pendingGroup(id: number): DuplicateGroup {
  return {
    id,
    kind: 'exact',
    status: 'pending',
    keeper_photo_id: id * 10,
    members: [id * 10, id * 10 + 1].map((photoId) => ({
      photo: photo(photoId),
      similarity_pct: 100,
      decision: null,
    })),
    reclaimable_bytes: 1000,
    created_at: '2026-01-01T00:00:00Z',
  }
}

let router: Router

async function mountView() {
  const wrapper = mount(DuplicatesView, { global: { plugins: [router] } })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('DuplicatesView', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    listGroupsMock.mockReset()
    summaryMock.mockReset()
    summaryMock.mockResolvedValue(summary())
    router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/duplicates', component: { template: '<div />' } },
        { path: '/duplicates/reviewed', component: { template: '<div />' } },
        { path: '/duplicates/dismissed', component: { template: '<div />' } },
        { path: '/quarantine', component: { template: '<div />' } },
      ],
    })
    router.push('/duplicates')
    await router.isReady()
  })

  it('is a queue of work still to do, not a record of everything', async () => {
    listGroupsMock.mockResolvedValue({ items: [pendingGroup(1)], total: 1, limit: 50, offset: 0 })

    await mountView()

    expect(listGroupsMock).toHaveBeenCalledWith(expect.objectContaining({ status: 'pending' }))
  })

  it('links to the groups already dealt with, with their counts', async () => {
    listGroupsMock.mockResolvedValue({ items: [pendingGroup(1)], total: 1, limit: 50, offset: 0 })

    const wrapper = await mountView()

    const links = wrapper.findAll('.reviewed-links a')
    expect(links.map((link) => link.text())).toEqual([
      'Reviewed (15) →',
      'Not duplicates (2) →',
    ])
    expect(links[0]!.attributes('href')).toBe('/duplicates/reviewed')
    expect(links[1]!.attributes('href')).toBe('/duplicates/dismissed')
  })

  it('an empty queue with decisions behind it does not claim there are no duplicates', async () => {
    listGroupsMock.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })

    const wrapper = await mountView()

    expect(wrapper.get('.empty-title').text()).toBe('Nothing left to review')
  })

  it('an empty queue with nothing decided still reads as no duplicates', async () => {
    summaryMock.mockResolvedValue(summary({ reviewed_groups: 0, dismissed_groups: 0 }))
    listGroupsMock.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })

    const wrapper = await mountView()

    expect(wrapper.get('.empty-title').text()).toBe('No duplicates found')
  })
})
