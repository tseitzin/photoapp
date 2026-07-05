import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import HomeView from '../HomeView.vue'
import { getStats } from '@/api/stats'
import type { Stats } from '@/api/stats'

vi.mock('@/api/stats', () => ({
  getStats: vi.fn<() => Promise<Stats>>(),
}))
vi.mock('@/api/photos', () => ({
  listPhotos: vi
    .fn<() => Promise<unknown>>()
    .mockResolvedValue({ items: [], total: 0, limit: 18, offset: 0 }),
  thumbnailUrl: (id: number) => `/thumb/${id}`,
}))
vi.mock('@/api/files', () => ({
  resetDeletionHistory: vi.fn<() => Promise<{ cleared: number }>>().mockResolvedValue({
    cleared: 3,
  }),
}))

import { resetDeletionHistory } from '@/api/files'

const getStatsMock = vi.mocked(getStats)
const resetMock = vi.mocked(resetDeletionHistory)

const STATS: Stats = {
  photos: 5575,
  storage_bytes: 13_000_000_000,
  folders: 86,
  missing: 0,
  duplicate_photos: 180,
  reclaimable_bytes: 400_000_000,
  last_scan_at: '2026-07-05T18:00:00Z',
  deleted_count: 42,
  space_saved_bytes: 2_147_483_648, // 2 GB
}

function cardValue(wrapper: ReturnType<typeof mount>, label: string): string | undefined {
  const card = wrapper
    .findAll('.stat-card')
    .find((c) => c.find('.stat-label').text() === label)
  return card?.find('.stat-value').text()
}

describe('HomeView lifetime tallies', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getStatsMock.mockReset()
    resetMock.mockClear()
  })

  it('shows deleted count and reclaimed space from the stats', async () => {
    getStatsMock.mockResolvedValue(STATS)
    const wrapper = mount(HomeView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()

    expect(cardValue(wrapper, 'DELETED')).toBe('42')
    expect(cardValue(wrapper, 'SPACE SAVED')).toBe('2.0 GB')
    // existing cards still present
    expect(cardValue(wrapper, 'PHOTOS')).toBe('5,575')
  })

  it('renders placeholder dashes when stats fail to load', async () => {
    getStatsMock.mockRejectedValue(new Error('offline'))
    const wrapper = mount(HomeView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()

    expect(cardValue(wrapper, 'DELETED')).toBe('—')
    expect(cardValue(wrapper, 'SPACE SAVED')).toBe('—')
  })

  it('confirming the reset calls the API and refetches the zeroed stats', async () => {
    getStatsMock.mockResolvedValueOnce(STATS)
    const wrapper = mount(HomeView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(cardValue(wrapper, 'DELETED')).toBe('42')

    // open the confirm dialog and confirm; stats come back zeroed
    getStatsMock.mockResolvedValueOnce({ ...STATS, deleted_count: 0, space_saved_bytes: 0 })
    await wrapper.get('.reset-btn').trigger('click')
    await wrapper.get('.btn--primary').trigger('click')
    await flushPromises()

    expect(resetMock).toHaveBeenCalledOnce()
    expect(cardValue(wrapper, 'DELETED')).toBe('0')
    expect(cardValue(wrapper, 'SPACE SAVED')).toBe('0 B')
  })

  it('cancelling the reset does not call the API', async () => {
    getStatsMock.mockResolvedValue(STATS)
    const wrapper = mount(HomeView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()

    await wrapper.get('.reset-btn').trigger('click')
    await wrapper.get('.btn:not(.btn--primary)').trigger('click')
    await flushPromises()

    expect(resetMock).not.toHaveBeenCalled()
    expect(cardValue(wrapper, 'DELETED')).toBe('42')
  })
})
