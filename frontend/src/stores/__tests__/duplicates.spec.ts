import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDuplicatesStore } from '../duplicates'
import { decideGroup, listGroups } from '@/api/duplicates'
import type { DuplicateGroup, DuplicateGroupPage, DuplicateSummary } from '@/api/duplicates'
import type { PhotoRead } from '@/api/photos'

vi.mock('@/api/duplicates', () => ({
  listGroups: vi.fn<() => Promise<DuplicateGroupPage>>(),
  decideGroup: vi.fn<() => Promise<unknown>>().mockResolvedValue({}),
  dismissGroup: vi.fn<() => Promise<unknown>>(),
  getDuplicateSummary: vi.fn<() => Promise<DuplicateSummary>>().mockResolvedValue({
    groups: 1,
    pending_groups: 1,
    reviewed_groups: 0,
    dismissed_groups: 0,
    exact_groups: 1,
    similar_groups: 0,
    member_photos: 3,
    marked_remove_count: 0,
    marked_remove_bytes: 0,
  }),
}))

const listGroupsMock = vi.mocked(listGroups)
const decideGroupMock = vi.mocked(decideGroup)

function photo(id: number, size = 1000): PhotoRead {
  return {
    id,
    root_id: 1,
    path: `/lib/p${id}.jpg`,
    filename: `p${id}.jpg`,
    ext: 'jpg',
    mime: 'image/jpeg',
    size_bytes: size,
    width: 100,
    height: 100,
    captured_at: null,
    camera_make: null,
    camera_model: null,
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
  }
}

function group(id: number, memberIds: number[], keeper: number): DuplicateGroup {
  return {
    id,
    kind: 'exact',
    status: 'pending',
    keeper_photo_id: keeper,
    members: memberIds.map((photoId) => ({
      photo: photo(photoId, photoId * 100),
      similarity_pct: 100,
      decision: null,
    })),
    reclaimable_bytes: 0,
    created_at: '2026-01-01T00:00:00Z',
  }
}

async function loadedStore(groups: DuplicateGroup[]) {
  listGroupsMock.mockResolvedValue({
    items: groups,
    total: groups.length,
    limit: 50,
    offset: 0,
  })
  const store = useDuplicatesStore()
  await store.load()
  return store
}

describe('duplicates store review flow', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listGroupsMock.mockReset()
    decideGroupMock.mockReset()
    decideGroupMock.mockResolvedValue({} as DuplicateGroup)
  })

  it('builds the pair queue keeper-vs-member across pending groups', async () => {
    const store = await loadedStore([group(1, [10, 11, 12], 10), group(2, [20, 21], 20)])

    store.startReview()

    expect(store.reviewing).toBe(true)
    expect(store.totalPairs).toBe(3)
    expect(store.currentPair?.a.photo.id).toBe(10)
    expect(store.currentPair?.b.photo.id).toBe(11)
  })

  it('keep A marks B for removal and advances, accumulating freed bytes', async () => {
    const store = await loadedStore([group(1, [10, 11, 12], 10)])
    store.startReview()

    await store.decide('keep_a')

    expect(decideGroupMock).toHaveBeenCalledWith(1, [
      { photo_id: 10, decision: 'keep' },
      { photo_id: 11, decision: 'remove' },
    ])
    expect(store.freedBytes).toBe(1100)
    expect(store.resolvedPairs).toBe(1)
    expect(store.currentPair?.b.photo.id).toBe(12)
  })

  it('keep B removes the old keeper and anchors remaining pairs on B', async () => {
    const store = await loadedStore([group(1, [10, 11, 12], 10)])
    store.startReview()

    await store.decide('keep_b')

    expect(decideGroupMock).toHaveBeenCalledWith(1, [
      { photo_id: 10, decision: 'remove' },
      { photo_id: 11, decision: 'keep' },
    ])
    expect(store.currentPair?.a.photo.id).toBe(11)
    expect(store.currentPair?.b.photo.id).toBe(12)
  })

  it('keep both records two keeps and frees nothing', async () => {
    const store = await loadedStore([group(1, [10, 11], 10)])
    store.startReview()

    await store.decide('keep_both')

    expect(decideGroupMock).toHaveBeenCalledWith(1, [
      { photo_id: 10, decision: 'keep' },
      { photo_id: 11, decision: 'keep' },
    ])
    expect(store.freedBytes).toBe(0)
  })

  it('finishing the last pair exits review mode', async () => {
    const store = await loadedStore([group(1, [10, 11], 10)])
    store.startReview()

    await store.decide('keep_a')

    expect(store.reviewing).toBe(false)
  })

  it('moves to the next group after one is finished', async () => {
    const store = await loadedStore([group(1, [10, 11], 10), group(2, [20, 21], 20)])
    store.startReview()

    await store.decide('keep_a')

    expect(store.currentPair?.group.id).toBe(2)
    expect(store.currentPair?.a.photo.id).toBe(20)
  })

  it('a failed decision surfaces the error and does not advance', async () => {
    const store = await loadedStore([group(1, [10, 11], 10)])
    store.startReview()
    decideGroupMock.mockRejectedValueOnce(new Error('409 conflict'))

    await store.decide('keep_a')

    expect(store.error).toContain('409')
    expect(store.resolvedPairs).toBe(0)
    expect(store.currentPair?.b.photo.id).toBe(11)
  })

  it('members already decided are excluded from the queue', async () => {
    const g = group(1, [10, 11, 12], 10)
    g.members[1]!.decision = 'remove'
    const store = await loadedStore([g])

    store.startReview()

    expect(store.totalPairs).toBe(1)
    expect(store.currentPair?.b.photo.id).toBe(12)
  })
})
