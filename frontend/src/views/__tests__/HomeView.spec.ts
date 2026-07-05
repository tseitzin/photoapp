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

const getStatsMock = vi.mocked(getStats)

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
})
