import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DuplicateGroupCard from '../DuplicateGroupCard.vue'
import type { DuplicateGroup, GroupStatus } from '@/api/duplicates'
import type { PhotoRead } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  thumbnailUrl: (id: number) => `/thumb/${id}`,
}))

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

function group(overrides: Partial<DuplicateGroup> = {}, memberCount = 2): DuplicateGroup {
  return {
    id: 1,
    kind: 'exact',
    status: 'pending',
    keeper_photo_id: 10,
    members: Array.from({ length: memberCount }, (_, index) => ({
      photo: photo(10 + index),
      similarity_pct: 100,
      decision: null,
    })),
    reclaimable_bytes: 2048,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('DuplicateGroupCard', () => {
  it('names the kind so exact copies and lookalikes are not confused', () => {
    const exact = mount(DuplicateGroupCard, { props: { group: group({ kind: 'exact' }) } })
    const similar = mount(DuplicateGroupCard, { props: { group: group({ kind: 'similar' }) } })

    expect(exact.get('.badge--exact').text()).toBe('Exact duplicates')
    expect(similar.get('.badge--similar').text()).toBe('Visually similar')
  })

  it.each<GroupStatus>(['pending', 'reviewed', 'dismissed'])('badges the %s status', (status) => {
    const wrapper = mount(DuplicateGroupCard, { props: { group: group({ status }) } })

    const badge = wrapper.get('.badge--status')
    expect(badge.text()).toBe(status)
    expect(badge.classes()).toContain(`badge--${status}`)
  })

  it('summarises how many photos and how much space is at stake', () => {
    const wrapper = mount(DuplicateGroupCard, { props: { group: group({}, 3) } })

    expect(wrapper.get('.card-sub').text()).toBe('3 photos · 2.0 KB reclaimable')
  })

  it('shows four thumbnails and counts the rest', () => {
    const wrapper = mount(DuplicateGroupCard, { props: { group: group({}, 7) } })

    expect(wrapper.findAll('.thumbs img')).toHaveLength(4)
    expect(wrapper.get('.more').text()).toBe('+3')
  })

  it('has no overflow marker when every photo is shown', () => {
    const wrapper = mount(DuplicateGroupCard, { props: { group: group({}, 4) } })

    expect(wrapper.findAll('.thumbs img')).toHaveLength(4)
    expect(wrapper.find('.more').exists()).toBe(false)
  })

  it('leaves the actions to the page, which differ by where the group is listed', () => {
    const wrapper = mount(DuplicateGroupCard, {
      props: { group: group({ status: 'reviewed' }) },
      slots: { actions: '<button class="review-again">Review again</button>' },
    })

    expect(wrapper.get('.card-actions .review-again').text()).toBe('Review again')
  })
})
