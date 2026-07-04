<script setup lang="ts">
import { onMounted } from 'vue'
import type { DuplicateKind } from '@/api/duplicates'
import { thumbnailUrl } from '@/api/photos'
import DuplicateCompare from '@/components/duplicates/DuplicateCompare.vue'
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
          {{ formatBytes(store.summary.marked_remove_bytes) }} to reclaim
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
      <article v-for="group in store.groups" :key="group.id" class="card">
        <div class="thumbs">
          <img
            v-for="member in group.members.slice(0, 4)"
            :key="member.photo.id"
            :src="thumbnailUrl(member.photo.id)"
            :alt="member.photo.filename"
            loading="lazy"
          />
          <span v-if="group.members.length > 4" class="more">
            +{{ group.members.length - 4 }}
          </span>
        </div>
        <div class="card-body">
          <p class="card-title">
            <span class="badge" :class="group.kind === 'exact' ? 'badge--exact' : 'badge--similar'">
              {{ group.kind === 'exact' ? 'Exact duplicates' : 'Visually similar' }}
            </span>
            <span class="badge badge--status" :class="`badge--${group.status}`">
              {{ group.status }}
            </span>
          </p>
          <p class="card-sub">
            {{ group.members.length }} photos ·
            {{ formatBytes(group.reclaimable_bytes) }} reclaimable
          </p>
        </div>
        <div class="card-actions">
          <button
            v-if="group.status === 'pending'"
            type="button"
            class="btn btn--primary"
            @click="store.startReview(group.id)"
          >
            Review
          </button>
          <button
            v-if="group.status === 'pending'"
            type="button"
            class="btn"
            @click="store.dismiss(group.id)"
          >
            Not duplicates
          </button>
        </div>
      </article>
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

.card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.thumbs {
  display: flex;
  align-items: center;
  gap: 4px;
}

.thumbs img {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 5px;
}

.more {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  padding: 0 4px;
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-title {
  margin: 0 0 4px;
  display: flex;
  gap: 6px;
}

.badge {
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
}

.badge--exact {
  background: color-mix(in oklab, var(--danger) 15%, transparent);
  color: var(--danger);
}

.badge--similar {
  background: var(--sel-chip-bg);
  color: var(--sel-chip-fg);
}

.badge--status {
  background: var(--chip);
  color: var(--sub);
  text-transform: capitalize;
}

.badge--reviewed {
  color: var(--success);
}

.card-sub {
  margin: 0;
  font-size: 12px;
  color: var(--sub);
}

.card-actions {
  display: flex;
  gap: 8px;
}
</style>
