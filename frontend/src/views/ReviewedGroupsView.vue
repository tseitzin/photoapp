<script setup lang="ts">
import { computed, watch } from 'vue'
import type { DuplicateKind, GroupStatus } from '@/api/duplicates'
import LoadMore from '@/components/common/LoadMore.vue'
import DuplicateCompare from '@/components/duplicates/DuplicateCompare.vue'
import DuplicateGroupCard from '@/components/duplicates/DuplicateGroupCard.vue'
import { useDuplicatesStore } from '@/stores/duplicates'
import { formatCount } from '@/utils/format'

/**
 * The record of duplicate groups already dealt with, kept off the Duplicates
 * queue so that page only shows work still to do.
 *
 * One component serves both states because they differ only in which status
 * they list — but they stay separate pages, because "I decided which to keep"
 * and "these were never duplicates" are different answers worth looking at
 * separately.
 */
const props = defineProps<{ status: Extract<GroupStatus, 'reviewed' | 'dismissed'> }>()

const store = useDuplicatesStore()

const COPY = {
  reviewed: {
    title: 'Reviewed',
    lead: 'Groups you have already decided on.',
    empty: 'Nothing reviewed yet',
    emptyHint: 'Groups you decide on in the Duplicates queue are kept here.',
    sibling: { to: '/duplicates/dismissed', label: 'Not duplicates' },
  },
  dismissed: {
    title: 'Not duplicates',
    lead: 'Groups you said were not duplicates of each other.',
    empty: 'Nothing marked as “not duplicates”',
    emptyHint: 'Use “Not duplicates” on a group in the Duplicates queue.',
    sibling: { to: '/duplicates/reviewed', label: 'Reviewed' },
  },
} as const

const copy = computed(() => COPY[props.status])
const siblingCount = computed(() =>
  props.status === 'reviewed'
    ? (store.summary?.dismissed_groups ?? 0)
    : (store.summary?.reviewed_groups ?? 0),
)

const KIND_OPTIONS: { value: DuplicateKind | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'exact', label: 'Exact' },
  { value: 'similar', label: 'Similar' },
]

// Watch rather than onMounted: the router reuses this component when moving
// between the two pages, so mount does not fire again.
watch(() => props.status, (status) => void store.setStatusFilter(status), { immediate: true })
</script>

<template>
  <DuplicateCompare v-if="store.reviewing" />

  <div v-else class="reviewed">
    <header class="head">
      <div class="heading">
        <RouterLink to="/duplicates" class="back">← Back to duplicates</RouterLink>
        <h1 class="title">{{ copy.title }}</h1>
        <p class="sub">
          {{ formatCount(store.total) }} groups · {{ copy.lead }}
        </p>
      </div>
      <div class="segmented" role="group" aria-label="Kind">
        <button
          v-for="option in KIND_OPTIONS"
          :key="option.value"
          type="button"
          class="seg-btn"
          :class="{ 'seg-btn--active': store.kindFilter === option.value }"
          @click="store.setKindFilter(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </header>

    <p v-if="store.error" class="error" role="alert">{{ store.error }}</p>
    <p v-if="store.loading" class="muted">Loading groups…</p>

    <p v-else-if="!store.groups.length" class="empty">
      <span class="empty-title">{{ copy.empty }}</span>
      {{ copy.emptyHint }}
    </p>

    <div v-else class="list">
      <DuplicateGroupCard v-for="group in store.groups" :key="group.id" :group="group">
        <template #actions>
          <button
            v-if="group.status === 'reviewed'"
            type="button"
            class="btn btn--primary"
            @click="store.reopen(group.id, true)"
          >
            Review again
          </button>
          <button type="button" class="btn" @click="store.reopen(group.id)">Reopen</button>
        </template>
      </DuplicateGroupCard>

      <LoadMore
        :shown="store.groups.length"
        :total="store.total"
        :has-more="store.hasMore"
        :busy="store.loadingMore"
        noun="groups"
        @more="store.loadMore()"
      />
    </div>

    <p class="cross-links">
      <RouterLink :to="copy.sibling.to" class="link">
        {{ copy.sibling.label }} ({{ formatCount(siblingCount) }}) →
      </RouterLink>
    </p>
  </div>
</template>

<style scoped>
.reviewed {
  max-width: 980px;
  width: 100%;
  margin: 0 auto;
  padding: 30px 32px;
}

.head {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 20px;
}

.heading {
  flex: 1;
}

.back {
  display: inline-block;
  margin-bottom: 6px;
  font-size: 12.5px;
  color: var(--sub);
  text-decoration: none;
}

.back:hover {
  color: var(--fg);
}

.title {
  margin: 0 0 4px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.sub {
  margin: 0;
  font-size: 12.5px;
  color: var(--sub);
}

.link {
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
}

.segmented {
  display: flex;
  background: var(--seg-bg);
  border-radius: 8px;
  padding: 2px;
  gap: 2px;
  font-size: 12.5px;
}

.seg-btn {
  border: 0;
  padding: 5px 13px;
  border-radius: 6px;
  background: transparent;
  color: var(--sub);
  font-weight: 500;
  cursor: pointer;
}

.seg-btn--active {
  background: var(--seg-active-bg);
  color: var(--seg-active-fg);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
}

.btn {
  padding: 7px 16px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--chip);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
}

.btn--primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
}

.error {
  padding: 9px 12px;
  border-radius: 8px;
  background: color-mix(in oklab, var(--danger) 12%, var(--card));
  font-size: 12.5px;
}

.muted {
  color: var(--muted);
}

.empty {
  text-align: center;
  color: var(--sub);
  padding: 60px 0;
}

.empty-title {
  display: block;
  font-size: 16px;
  font-weight: 600;
  color: var(--fg);
  margin-bottom: 6px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cross-links {
  margin: 22px 0 0;
  padding-top: 16px;
  border-top: 1px solid var(--divider);
  font-size: 12.5px;
}
</style>
