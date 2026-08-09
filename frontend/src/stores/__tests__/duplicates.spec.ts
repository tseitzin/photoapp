import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDuplicatesStore } from '../duplicates'
import { decideGroup, dismissGroup, listGroups, reopenGroup } from '@/api/duplicates'
import type { DuplicateGroup, DuplicateGroupPage, DuplicateSummary } from '@/api/duplicates'
import type { PhotoRead } from '@/api/photos'

vi.mock('@/api/duplicates', () => ({
  listGroups: vi.fn<() => Promise<DuplicateGroupPage>>(),
  decideGroup: vi.fn<() => Promise<unknown>>().mockResolvedValue({}),
  dismissGroup: vi.fn<() => Promise<unknown>>(),
  reopenGroup: vi.fn<() => Promise<unknown>>().mockResolvedValue({}),
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
const reopenGroupMock = vi.mocked(reopenGroup)
const dismissGroupMock = vi.mocked(dismissGroup)

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
    marked_for_deletion: false,
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
    reopenGroupMock.mockReset()
    reopenGroupMock.mockResolvedValue({} as DuplicateGroup)
  })

  it('reopen un-reviews a group and can jump straight back into reviewing it', async () => {
    const reviewed = group(1, [10, 11], 10)
    reviewed.status = 'reviewed'
    reviewed.members[0]!.decision = 'keep'
    reviewed.members[1]!.decision = 'remove'
    const store = await loadedStore([reviewed])
    // The endpoint responds with the reopened group: pending, decisions cleared.
    reopenGroupMock.mockResolvedValue(group(1, [10, 11], 10))

    await store.reopen(1, true)

    expect(reopenGroupMock).toHaveBeenCalledWith(1)
    expect(store.reviewing).toBe(true)
    expect(store.currentPair?.group.id).toBe(1)
    expect(store.currentPair?.a.photo.id).toBe(10)
  })

  it('reopen without review returns the group to pending in place', async () => {
    const dismissed = group(3, [30, 31], 30)
    dismissed.status = 'dismissed'
    const store = await loadedStore([dismissed])
    reopenGroupMock.mockResolvedValue(group(3, [30, 31], 30))

    await store.reopen(3)

    expect(reopenGroupMock).toHaveBeenCalledWith(3)
    expect(store.reviewing).toBe(false)
    expect(store.groups[0]!.status).toBe('pending')
    // Updated from the response, not by refetching the whole list.
    expect(listGroupsMock).toHaveBeenCalledTimes(1)
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

  it('remove both marks both for removal with force and frees both sizes', async () => {
    const store = await loadedStore([group(1, [10, 11], 10)])
    store.startReview()

    await store.decide('remove_both')

    expect(decideGroupMock).toHaveBeenCalledWith(
      1,
      [
        { photo_id: 10, decision: 'remove' },
        { photo_id: 11, decision: 'remove' },
      ],
      true,
    )
    expect(store.freedBytes).toBe(2100) // sizes 1000 + 1100
    expect(store.reviewing).toBe(false) // the 2-photo group is fully resolved
  })

  it('remove both in a 3-photo group re-anchors on the surviving member', async () => {
    const store = await loadedStore([group(1, [10, 11, 12], 10)])
    store.startReview()

    await store.decide('remove_both') // removes 10 (keeper) and 11

    // 12 becomes the survivor; nothing left to pair, so review ends
    expect(store.reviewing).toBe(false)
    expect(store.freedBytes).toBe(2100)
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

describe('duplicates list paging', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listGroupsMock.mockReset()
    dismissGroupMock.mockReset()
  })

  function page(groups: DuplicateGroup[], total: number, offset = 0): DuplicateGroupPage {
    return { items: groups, total, limit: 50, offset }
  }

  it('load more appends the next page rather than replacing it', async () => {
    listGroupsMock.mockResolvedValueOnce(page([group(1, [10, 11], 10)], 2))
    const store = useDuplicatesStore()
    await store.load()
    listGroupsMock.mockResolvedValueOnce(page([group(2, [20, 21], 20)], 2, 1))

    await store.loadMore()

    expect(store.groups.map((g) => g.id)).toEqual([1, 2])
    // Offset comes from what is loaded, so a dropped group cannot shift the window.
    expect(listGroupsMock).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 1 }))
  })

  it('load more stops once every group is loaded', async () => {
    listGroupsMock.mockResolvedValue(page([group(1, [10, 11], 10)], 1))
    const store = useDuplicatesStore()
    await store.load()

    expect(store.hasMore).toBe(false)

    await store.loadMore()

    expect(listGroupsMock).toHaveBeenCalledTimes(1)
  })

  it('a dismissed group leaves a list that only shows pending groups', async () => {
    listGroupsMock.mockResolvedValue(page([group(1, [10, 11], 10), group(2, [20, 21], 20)], 2))
    const store = useDuplicatesStore()
    await store.setStatusFilter('pending')
    const nowDismissed = group(1, [10, 11], 10)
    nowDismissed.status = 'dismissed'
    dismissGroupMock.mockResolvedValue(nowDismissed)

    await store.dismiss(1)

    expect(store.groups.map((g) => g.id)).toEqual([2])
    expect(store.total).toBe(1)
  })

  it('a dismissed group stays put on a list that shows every status', async () => {
    listGroupsMock.mockResolvedValue(page([group(1, [10, 11], 10)], 1))
    const store = useDuplicatesStore()
    await store.load()
    const nowDismissed = group(1, [10, 11], 10)
    nowDismissed.status = 'dismissed'
    dismissGroupMock.mockResolvedValue(nowDismissed)

    await store.dismiss(1)

    expect(store.groups.map((g) => g.id)).toEqual([1])
    expect(store.groups[0]!.status).toBe('dismissed')
  })

  it('switching status does not show the previous page groups', async () => {
    listGroupsMock.mockResolvedValue(page([group(1, [10, 11], 10)], 1))
    const store = useDuplicatesStore()
    await store.setStatusFilter('pending')
    let seenDuringFetch: number[] = []
    listGroupsMock.mockImplementationOnce(async () => {
      seenDuringFetch = store.groups.map((g) => g.id)
      return page([group(9, [90, 91], 90)], 1)
    })

    await store.setStatusFilter('reviewed')

    expect(seenDuringFetch).toEqual([])
    expect(store.groups.map((g) => g.id)).toEqual([9])
  })

  it('the status filter is sent to the API', async () => {
    listGroupsMock.mockResolvedValue(page([], 0))
    const store = useDuplicatesStore()

    await store.setStatusFilter('reviewed')

    expect(listGroupsMock).toHaveBeenCalledWith(expect.objectContaining({ status: 'reviewed' }))
  })
})
