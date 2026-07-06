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
} from '@/api/duplicates'

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
  const error = ref<string | null>(null)
  const kindFilter = ref<DuplicateKind | 'all'>('all')
  const summary = ref<DuplicateSummary | null>(null)

  const reviewing = ref(false)
  const reviewItems = ref<ReviewItem[]>([])
  const totalPairs = ref(0)
  const resolvedPairs = ref(0)
  const freedBytes = ref(0)

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [page, summaryResult] = await Promise.all([
        listGroups({
          kind: kindFilter.value === 'all' ? undefined : kindFilter.value,
          limit: PAGE_SIZE,
        }),
        getDuplicateSummary(),
      ])
      groups.value = page.items
      total.value = page.total
      summary.value = summaryResult
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  function setKindFilter(kind: DuplicateKind | 'all'): Promise<void> {
    kindFilter.value = kind
    return load()
  }

  function startReview(groupId?: number): void {
    const candidates = groups.value.filter(
      (group) =>
        group.status === 'pending' && (groupId === undefined || group.id === groupId),
    )
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
    try {
      // remove_both may mark every member of a 2-photo group — force past the guard.
      await (choice === 'remove_both'
        ? decideGroup(item.group.id, decisions, true)
        : decideGroup(item.group.id, decisions))
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      return
    }

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
      void load()
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
    void load()
  }

  async function dismiss(groupId: number): Promise<void> {
    try {
      await dismissGroup(groupId)
      await load()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  /** Undo a review/dismissal, returning the group to 'pending'. Pass
   *  andReview to jump straight back into reviewing it. */
  async function reopen(groupId: number, andReview = false): Promise<void> {
    try {
      await reopenGroup(groupId)
      await load()
      if (andReview) startReview(groupId)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  return {
    groups,
    total,
    loading,
    error,
    kindFilter,
    summary,
    reviewing,
    totalPairs,
    resolvedPairs,
    freedBytes,
    currentPair,
    load,
    setKindFilter,
    startReview,
    decide,
    skip,
    stopReview,
    dismiss,
    reopen,
  }
})
