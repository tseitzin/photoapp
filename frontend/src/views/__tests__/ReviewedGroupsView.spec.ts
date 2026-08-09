import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory, type Router } from 'vue-router'
import ReviewedGroupsView from '../ReviewedGroupsView.vue'
import { listGroups, reopenGroup } from '@/api/duplicates'
import type { DuplicateGroup, DuplicateGroupPage, DuplicateSummary } from '@/api/duplicates'
import type { PhotoRead } from '@/api/photos'

vi.mock('@/api/duplicates', () => ({
  listGroups: vi.fn<() => Promise<DuplicateGroupPage>>(),
  decideGroup: vi.fn<() => Promise<unknown>>(),
  dismissGroup: vi.fn<() => Promise<unknown>>(),
  reopenGroup: vi.fn<() => Promise<unknown>>(),
  getDuplicateSummary: vi.fn<() => Promise<DuplicateSummary>>().mockResolvedValue({
    groups: 3,
    pending_groups: 1,
    reviewed_groups: 1,
    dismissed_groups: 1,
    exact_groups: 3,
    similar_groups: 0,
    member_photos: 6,
    marked_remove_count: 0,
    marked_remove_bytes: 0,
  }),
}))
vi.mock('@/api/photos', () => ({
  thumbnailUrl: (id: number) => `/thumb/${id}`,
  previewUrl: (id: number) => `/preview/${id}`,
}))

const listGroupsMock = vi.mocked(listGroups)
const reopenGroupMock = vi.mocked(reopenGroup)

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

function group(id: number, status: DuplicateGroup['status']): DuplicateGroup {
  return {
    id,
    kind: 'exact',
    status,
    keeper_photo_id: id * 10,
    members: [id * 10, id * 10 + 1].map((photoId) => ({
      photo: photo(photoId),
      similarity_pct: 100,
      decision: status === 'reviewed' ? 'keep' : null,
    })),
    reclaimable_bytes: 1000,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function page(groups: DuplicateGroup[]): DuplicateGroupPage {
  return { items: groups, total: groups.length, limit: 50, offset: 0 }
}

let router: Router

async function mountAt(status: 'reviewed' | 'dismissed') {
  const wrapper = mount(ReviewedGroupsView, {
    props: { status },
    global: { plugins: [router] },
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('ReviewedGroupsView', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    listGroupsMock.mockReset()
    reopenGroupMock.mockReset()
    router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/duplicates', component: { template: '<div />' } },
        { path: '/duplicates/reviewed', component: { template: '<div />' } },
        { path: '/duplicates/dismissed', component: { template: '<div />' } },
      ],
    })
    router.push('/duplicates/reviewed')
    await router.isReady()
  })

  it('asks the API only for groups in the state this page shows', async () => {
    listGroupsMock.mockResolvedValue(page([group(1, 'reviewed')]))

    await mountAt('reviewed')

    expect(listGroupsMock).toHaveBeenCalledWith(expect.objectContaining({ status: 'reviewed' }))
  })

  it('titles itself for the state it lists', async () => {
    listGroupsMock.mockResolvedValue(page([]))

    const reviewed = await mountAt('reviewed')
    const dismissed = await mountAt('dismissed')

    expect(reviewed.get('.title').text()).toBe('Reviewed')
    expect(dismissed.get('.title').text()).toBe('Not duplicates')
  })

  it('lists the groups already dealt with', async () => {
    listGroupsMock.mockResolvedValue(page([group(1, 'reviewed'), group(2, 'reviewed')]))

    const wrapper = await mountAt('reviewed')

    expect(wrapper.findAll('.card')).toHaveLength(2)
    expect(wrapper.get('.sub').text()).toContain('2 groups')
  })

  it('offers a way back to the queue', async () => {
    listGroupsMock.mockResolvedValue(page([]))

    const wrapper = await mountAt('reviewed')

    expect(wrapper.get('.back').attributes('href')).toBe('/duplicates')
  })

  it('says what is missing rather than claiming there are no duplicates', async () => {
    listGroupsMock.mockResolvedValue(page([]))

    const wrapper = await mountAt('reviewed')

    expect(wrapper.get('.empty-title').text()).toBe('Nothing reviewed yet')
  })

  it('reopening a reviewed group starts a review of it, from this page', async () => {
    // The regression this guards: startReview used to filter the loaded list
    // for pending groups, and this page has none — so it did nothing at all.
    listGroupsMock.mockResolvedValue(page([group(1, 'reviewed')]))
    reopenGroupMock.mockResolvedValue(group(1, 'pending'))
    const wrapper = await mountAt('reviewed')

    await wrapper.get('.btn--primary').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()

    expect(reopenGroupMock).toHaveBeenCalledWith(1)
    expect(wrapper.findComponent({ name: 'DuplicateCompare' }).exists()).toBe(true)
  })

  it('a dismissed group offers only Reopen, since there is nothing to re-decide', async () => {
    listGroupsMock.mockResolvedValue(page([group(1, 'dismissed')]))

    const wrapper = await mountAt('dismissed')

    const buttons = wrapper.findAll('.card-actions button').map((b) => b.text())
    expect(buttons).toEqual(['Reopen'])
  })

  it('a reopened group leaves this page', async () => {
    listGroupsMock.mockResolvedValue(page([group(1, 'reviewed'), group(2, 'reviewed')]))
    reopenGroupMock.mockResolvedValue(group(1, 'pending'))
    const wrapper = await mountAt('reviewed')

    // The second button on the first card is the plain Reopen.
    await wrapper.findAll('.card')[0]!.findAll('button')[1]!.trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.card')).toHaveLength(1)
  })
})
