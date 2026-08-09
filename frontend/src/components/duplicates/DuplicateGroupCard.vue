<script setup lang="ts">
import type { DuplicateGroup } from '@/api/duplicates'
import { thumbnailUrl } from '@/api/photos'
import { formatBytes } from '@/utils/format'

/**
 * One duplicate group as a row. Rendered by the Duplicates queue and by both
 * review-history pages, which is why the actions are a slot: the same group
 * offers different choices depending on where you are looking at it from.
 */
defineProps<{ group: DuplicateGroup }>()

const THUMBS_SHOWN = 4
</script>

<template>
  <article class="card">
    <div class="thumbs">
      <img
        v-for="member in group.members.slice(0, THUMBS_SHOWN)"
        :key="member.photo.id"
        :src="thumbnailUrl(member.photo.id)"
        :alt="member.photo.filename"
        loading="lazy"
      />
      <span v-if="group.members.length > THUMBS_SHOWN" class="more">
        +{{ group.members.length - THUMBS_SHOWN }}
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
        {{ group.members.length }} photos · {{ formatBytes(group.reclaimable_bytes) }} reclaimable
      </p>
    </div>
    <div class="card-actions">
      <slot name="actions" :group="group" />
    </div>
  </article>
</template>

<style scoped>
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
