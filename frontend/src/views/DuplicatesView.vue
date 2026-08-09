<script setup lang="ts">
import { onMounted } from 'vue'
import type { DuplicateKind } from '@/api/duplicates'
import LoadMore from '@/components/common/LoadMore.vue'
import DuplicateCompare from '@/components/duplicates/DuplicateCompare.vue'
import DuplicateGroupCard from '@/components/duplicates/DuplicateGroupCard.vue'
import { useDuplicatesStore } from '@/stores/duplicates'
import { formatBytes, formatCount } from '@/utils/format'

const store = useDuplicatesStore()

onMounted(() => void store.load())

const KIND_OPTIONS: { value: DuplicateKind | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'exact', label: 'Exact' },
  { value: 'similar', label: 'Similar' },
]
</script>

<template>
  <DuplicateCompare v-if="store.reviewing" />

  <div v-else class="duplicates">
    <header class="head">
      <div>
        <h1 class="title">Duplicates</h1>
        <p v-if="store.summary" class="sub">
          {{ formatCount(store.summary.pending_groups) }} groups to review ·
          {{ formatCount(store.summary.marked_remove_count) }} photos marked ·
          {{ formatBytes(store.summary.marked_remove_bytes) }} to reclaim ·
          <RouterLink to="/quarantine" class="link">apply removals →</RouterLink>
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
      <button
        type="button"
        class="btn btn--primary"
        :disabled="!store.groups.some((g) => g.status === 'pending')"
        @click="store.startReview()"
      >
        Review all
      </button>
    </header>

    <p v-if="store.error" class="error" role="alert">{{ store.error }}</p>
    <p v-if="store.loading" class="muted">Loading duplicate groups…</p>

    <p v-else-if="!store.groups.length" class="empty">
      <span class="empty-title">No duplicates found</span>
      Run a scan and check back — exact copies and visually similar photos will show up here.
    </p>

    <div v-else class="list">
      <DuplicateGroupCard v-for="group in store.groups" :key="group.id" :group="group">
        <template #actions>
          <template v-if="group.status === 'pending'">
            <button type="button" class="btn btn--primary" @click="store.startReview(group.id)">
              Review
            </button>
            <button type="button" class="btn" @click="store.dismiss(group.id)">
              Not duplicates
            </button>
          </template>
          <button
            v-else-if="group.status === 'reviewed'"
            type="button"
            class="btn btn--primary"
            @click="store.reopen(group.id, true)"
          >
            Review again
          </button>
          <button
            v-else-if="group.status === 'dismissed'"
            type="button"
            class="btn"
            @click="store.reopen(group.id)"
          >
            Reopen
          </button>
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
  </div>
</template>

<style scoped>
.duplicates {
  max-width: 980px;
  width: 100%;
  margin: 0 auto;
  padding: 30px 32px;
}

.head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.head > div:first-child {
  flex: 1;
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

.btn--primary:disabled {
  opacity: 0.5;
  cursor: default;
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

</style>
