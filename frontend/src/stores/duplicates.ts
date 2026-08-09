import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  decideGroup,
  dismissGroup,
  getDuplicateSummary,
  listGroups,
  reopenGroup,
  type DuplicateGroup,
  type DuplicateKind,
  type DuplicateMember,
  type DuplicateSummary,
  type GroupStatus,
} from '@/api/duplicates'

// The endpoint caps limit at 100; "Load more" walks the list a page at a time.
const PAGE_SIZE = 50

export type PairChoice = 'keep_a' | 'keep_b' | 'keep_both' | 'remove_both'

interface ReviewItem {
  group: DuplicateGroup
  keeperId: number
  /** Members still awaiting a pair decision (never contains the keeper). */
  remaining: number[]
}

export interface ReviewPair {
  group: DuplicateGroup
  a: DuplicateMember
  b: DuplicateMember
}

export const useDuplicatesStore = defineStore('duplicates', () => {
  const groups = ref<DuplicateGroup[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref<string | null>(null)
  const kindFilter = ref<DuplicateKind | 'all'>('all')
  /** Which review state this page lists; null means every status. */
  const statusFilter = ref<GroupStatus | null>(null)
  const summary = ref<DuplicateSummary | null>(null)

  const reviewing = ref(false)
  const reviewItems = ref<ReviewItem[]>([])
  const totalPairs = ref(0)
  const resolvedPairs = ref(0)
  const freedBytes = ref(0)

  // A slow first page must not overwrite a newer one — reachable by switching
  // kind twice quickly, or by navigating between the review-state pages.
  let fetchSeq = 0

  const hasMore = computed(() => groups.value.length < total.value)

  function query(offset: number) {
    return {
      kind: kindFilter.value === 'all' ? undefined : kindFilter.value,
      status: statusFilter.value ?? undefined,
      limit: PAGE_SIZE,
      offset,
    }
  }

  async function load(): Promise<void> {
    const seq = ++fetchSeq
    loading.value = true
    error.value = null
    try {
      const [page, summaryResult] = await Promise.all([
        listGroups(query(0)),
        getDuplicateSummary(),
      ])
      if (seq !== fetchSeq) return
      groups.value = page.items
      total.value = page.total
      summary.value = summaryResult
    } catch (e) {
      if (seq !== fetchSeq) return
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (seq === fetchSeq) loading.value = false
    }
  }

  /** Append the next page. Offset comes from what is already loaded, so it
   *  stays correct after a group has been dropped from the list. */
  async function loadMore(): Promise<void> {
    if (loading.value || loadingMore.value || !hasMore.value) return
    const seq = fetchSeq
    loadingMore.value = true
    try {
      const page = await listGroups(query(groups.value.length))
      if (seq !== fetchSeq) return
      groups.value = [...groups.value, ...page.items]
      total.value = page.total
    } catch (e) {
      if (seq !== fetchSeq) return
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loadingMore.value = false
    }
  }

  /**
   * Fold a group the API just returned back into the list.
   *
   * Replacing in place rather than refetching keeps the pages already loaded —
   * and dropping a group that no longer matches this page's filter is what
   * makes a reviewed group leave the Duplicates queue.
   */
  function applyUpdatedGroup(updated: DuplicateGroup): void {
    const index = groups.value.findIndex((group) => group.id === updated.id)
    if (index === -1) return
    if (statusFilter.value === null || updated.status === statusFilter.value) {
      groups.value[index] = updated
      return
    }
    groups.value.splice(index, 1)
    total.value = Math.max(0, total.value - 1)
  }

  async function refreshSummary(): Promise<void> {
    try {
      summary.value = await getDuplicateSummary()
    } catch {
      // The counts in the header are decoration; a stale one is not worth an
      // error banner over an action that already succeeded.
    }
  }

  function setKindFilter(kind: DuplicateKind | 'all'): Promise<void> {
    kindFilter.value = kind
    return load()
  }

  /** Point the list at one review state (or all of them) and reload. */
  function setStatusFilter(status: GroupStatus | null): Promise<void> {
    if (statusFilter.value !== status) {
      // Clear first: navigating between pages must not flash the other's groups.
      statusFilter.value = status
      groups.value = []
      total.value = 0
    }
    return load()
  }

  /** Queue an explicit set of groups for review, whichever page they came from. */
  function startReviewOf(candidates: DuplicateGroup[]): void {
    reviewItems.value = candidates
      .map((group) => {
        const keeperId = group.keeper_photo_id ?? group.members[0]!.photo.id
        return {
          group,
          keeperId,
          remaining: group.members
            .filter((m) => m.photo.id !== keeperId && m.decision === null)
            .map((m) => m.photo.id),
        }
      })
      .filter((item) => item.remaining.length > 0)
    totalPairs.value = reviewItems.value.reduce((sum, item) => sum + item.remaining.length, 0)
    resolvedPairs.value = 0
    freedBytes.value = 0
    reviewing.value = reviewItems.value.length > 0
  }

  function startReview(groupId?: number): void {
    startReviewOf(
      groups.value.filter(
        (group) => group.status === 'pending' && (groupId === undefined || group.id === groupId),
      ),
    )
  }

  const currentPair = computed<ReviewPair | null>(() => {
    const item = reviewItems.value.find((entry) => entry.remaining.length > 0)
    if (!item) return null
    const byId = new Map(item.group.members.map((m) => [m.photo.id, m]))
    const a = byId.get(item.keeperId)
    const b = byId.get(item.remaining[0]!)
    return a && b ? { group: item.group, a, b } : null
  })

  async function decide(choice: PairChoice): Promise<void> {
    const pair = currentPair.value
    const item = reviewItems.value.find((entry) => entry.remaining.length > 0)
    if (!pair || !item) return
    const { a, b } = pair

    const decisionByChoice: Record<PairChoice, ['keep' | 'remove', 'keep' | 'remove']> = {
      keep_a: ['keep', 'remove'],
      keep_b: ['remove', 'keep'],
      keep_both: ['keep', 'keep'],
      remove_both: ['remove', 'remove'],
    }
    const [decA, decB] = decisionByChoice[choice]
    const decisions = [
      { photo_id: a.photo.id, decision: decA },
      { photo_id: b.photo.id, decision: decB },
    ]
    let updated: DuplicateGroup
    try {
      // remove_both may mark every member of a 2-photo group — force past the guard.
      updated = await (choice === 'remove_both'
        ? decideGroup(item.group.id, decisions, true)
        : decideGroup(item.group.id, decisions))
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      return
    }
    applyUpdatedGroup(updated)

    if (decB === 'remove') freedBytes.value += b.photo.size_bytes
    if (decA === 'remove') freedBytes.value += a.photo.size_bytes
    item.remaining = item.remaining.filter((id) => id !== b.photo.id)
    if (choice === 'keep_b') {
      item.keeperId = b.photo.id // the survivor anchors the remaining pairs
    } else if (choice === 'remove_both' && item.remaining.length > 0) {
      // both shown photos are gone; re-anchor to the next remaining member
      item.keeperId = item.remaining[0]!
      item.remaining = item.remaining.slice(1)
    }
    resolvedPairs.value += 1
    if (!currentPair.value) {
      reviewing.value = false
      void refreshSummary()
    }
  }

  function skip(): void {
    const index = reviewItems.value.findIndex((entry) => entry.remaining.length > 0)
    if (index === -1) return
    const item = reviewItems.value[index]!
    if (item.remaining.length > 1) {
      item.remaining = [...item.remaining.slice(1), item.remaining[0]!]
    } else {
      // Single pair left in this group: move the whole group to the back.
      reviewItems.value = [
        ...reviewItems.value.slice(0, index),
        ...reviewItems.value.slice(index + 1),
        item,
      ]
    }
  }

  function stopReview(): void {
    reviewing.value = false
    void refreshSummary()
  }

  async function dismiss(groupId: number): Promise<void> {
    try {
      applyUpdatedGroup(await dismissGroup(groupId))
      await refreshSummary()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  /** Undo a review/dismissal, returning the group to 'pending'. Pass
   *  andReview to jump straight back into reviewing it. */
  async function reopen(groupId: number, andReview = false): Promise<void> {
    try {
      const reopened = await reopenGroup(groupId)
      applyUpdatedGroup(reopened)
      await refreshSummary()
      // Seeded from the response, not from the list: on the reviewed page the
      // list holds no pending groups, so filtering it would find nothing.
      if (andReview) startReviewOf([reopened])
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  return {
    groups,
    total,
    loading,
    loadingMore,
    hasMore,
    error,
    kindFilter,
    statusFilter,
    summary,
    reviewing,
    totalPairs,
    resolvedPairs,
    freedBytes,
    currentPair,
    load,
    loadMore,
    setKindFilter,
    setStatusFilter,
    startReview,
    startReviewOf,
    decide,
    skip,
    stopReview,
    dismiss,
    reopen,
  }
})
