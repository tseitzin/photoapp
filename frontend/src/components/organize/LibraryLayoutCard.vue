<script setup lang="ts">
import { useOrganizeStore } from '@/stores/organize'
import { formatCount } from '@/utils/format'

/**
 * Where the library lives right now, shown before a destination is chosen.
 *
 * A library once ended up as the same date structure in two places, and the
 * only way to notice was to browse the folder tree afterwards. Listing the
 * locations makes a split visible before a run creates one.
 */
const store = useOrganizeStore()

/** ".../Camera Roll/Organized" — enough to tell two locations apart. */
function shortPath(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts.length <= 3 ? path : `…/${parts.slice(-3).join('/')}`
}
</script>

<template>
  <section v-if="store.locations.length" class="card">
    <h2 class="title">Your library today</h2>
    <ul class="locations">
      <li v-for="location in store.locations" :key="location.path" class="row">
        <span class="path" :title="location.path">{{ shortPath(location.path) }}</span>
        <span class="count">{{ formatCount(location.photos) }}</span>
      </li>
    </ul>
    <p v-if="store.locations.length > 1" class="note">
      Your photos are in {{ store.locations.length }} places. Organizing them all into one
      destination brings them together.
    </p>
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: var(--shadow-card);
}

.title {
  margin: 0 0 10px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--sub);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.locations {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 12.5px;
}

.path {
  font-family: var(--font-mono);
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.count {
  color: var(--sub);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--muted);
}
</style>
