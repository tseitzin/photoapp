<script setup lang="ts">
import { onMounted } from 'vue'
import type { PhotoSort } from '@/api/photos'
import FolderTree from '@/components/library/FolderTree.vue'
import PhotoGrid from '@/components/library/PhotoGrid.vue'
import { useLibraryStore } from '@/stores/library'
import { formatCount } from '@/utils/format'

const store = useLibraryStore()

onMounted(() => {
  if (!store.photos.length) void store.init()
})

const SORT_OPTIONS: { value: PhotoSort; label: string }[] = [
  { value: 'captured_desc', label: 'Capture date ↓' },
  { value: 'captured_asc', label: 'Capture date ↑' },
  { value: 'name_asc', label: 'Filename A–Z' },
  { value: 'name_desc', label: 'Filename Z–A' },
  { value: 'size_desc', label: 'File size ↓' },
  { value: 'size_asc', label: 'File size ↑' },
]
</script>

<template>
  <div class="library">
    <aside class="sidebar">
      <FolderTree />
    </aside>

    <section class="center">
      <div class="subheader">
        <span class="breadcrumb">All photos</span>
        <span class="total">{{ formatCount(store.total) }} photos</span>
        <span class="spacer" />
        <label class="control">
          Sort
          <select
            class="select"
            :value="store.sort"
            @change="store.setSort(($event.target as HTMLSelectElement).value as PhotoSort)"
          >
            <option v-for="option in SORT_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
        <input
          v-model.number="store.tileSize"
          class="size-slider"
          type="range"
          min="84"
          max="220"
          aria-label="Thumbnail size"
        />
      </div>

      <div class="grid-scroll">
        <p v-if="store.loading" class="state">Loading photos…</p>
        <div v-else-if="store.error" class="state state--error">
          <p>Can’t reach the library service</p>
          <code class="error-detail">{{ store.error }}</code>
          <button type="button" class="retry" @click="store.reload()">Retry</button>
        </div>
        <div v-else-if="store.total === 0" class="state">
          <p class="state-title">No photos indexed yet</p>
          <p class="state-sub">Add a folder and run a scan to build your library.</p>
          <RouterLink to="/scan" class="state-action">Run a scan</RouterLink>
        </div>
        <PhotoGrid v-else />
      </div>
    </section>
  </div>
</template>

<style scoped>
.library {
  flex: 1;
  display: flex;
  min-height: 0;
}

.sidebar {
  width: 266px;
  flex: none;
  background: var(--sidebar);
  border-right: 1px solid var(--border);
  min-height: 0;
}

.center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--grid-bg);
}

.subheader {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 18px;
  background: var(--bar);
  border-bottom: 1px solid var(--border);
}

.breadcrumb {
  font-weight: 600;
}

.total {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}

.spacer {
  flex: 1;
}

.control {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--sub);
}

.select {
  background: var(--chip);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 12.5px;
}

.size-slider {
  width: 140px;
  accent-color: var(--accent);
}

.grid-scroll {
  flex: 1;
  overflow: auto;
  min-height: 0;
}

.state {
  padding: 48px 24px;
  text-align: center;
  color: var(--sub);
}

.state-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--fg);
  margin: 0 0 6px;
}

.state-sub {
  margin: 0 0 14px;
}

.state-action {
  display: inline-block;
  padding: 7px 16px;
  border-radius: 9px;
  background: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
  text-decoration: none;
}

.state--error .error-detail {
  display: block;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--danger);
  margin: 8px 0 14px;
}

.retry {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--fg);
  cursor: pointer;
}

@media (max-width: 900px) {
  .sidebar {
    display: none;
  }
}
</style>
