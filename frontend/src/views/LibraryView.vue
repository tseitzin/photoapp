<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { PhotoSort } from '@/api/photos'
import FilterPanel from '@/components/library/FilterPanel.vue'
import FolderTree from '@/components/library/FolderTree.vue'
import PhotoGrid from '@/components/library/PhotoGrid.vue'
import PhotoLightbox from '@/components/library/PhotoLightbox.vue'
import SelectionBar from '@/components/library/SelectionBar.vue'
import { PAGE_SIZE_OPTIONS, useLibraryStore, type PageSize } from '@/stores/library'
import { formatCount } from '@/utils/format'

const store = useLibraryStore()
const gridScroll = ref<HTMLElement | null>(null)

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

function pageSizeLabel(size: PageSize): string {
  return size === 'all' ? 'All' : String(size)
}

function parsePageSize(raw: string): PageSize {
  return raw === 'all' ? 'all' : Number(raw)
}

/** Run a page change, then return the grid to the top so the new page is visible. */
async function withScrollReset(action: () => Promise<void>): Promise<void> {
  await action()
  gridScroll.value?.scrollTo({ top: 0 })
}

const breadcrumb = computed(() => {
  if (!store.activeFolder) return 'All photos'
  return store.activeFolder.split('/').pop() ?? store.activeFolder
})
</script>

<template>
  <div class="library">
    <aside class="sidebar">
      <FolderTree />
    </aside>

    <section class="center">
      <div class="subheader">
        <span class="breadcrumb" :title="store.activeFolder ?? undefined">{{ breadcrumb }}</span>
        <button
          v-if="store.activeFolder"
          type="button"
          class="breadcrumb-clear"
          aria-label="Show all photos"
          @click="store.setFolder(null)"
        >
          × All photos
        </button>
        <span class="total">{{ formatCount(store.total) }} photos</span>
        <RouterLink v-if="store.markedOnPage > 0" to="/quarantine" class="marked-link">
          🗑 {{ formatCount(store.markedOnPage) }} marked · review →
        </RouterLink>
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
        <label class="control">
          Show
          <select
            class="select"
            :value="String(store.pageSize)"
            @change="
              withScrollReset(() =>
                store.setPageSize(parsePageSize(($event.target as HTMLSelectElement).value)),
              )
            "
          >
            <option v-for="option in PAGE_SIZE_OPTIONS" :key="String(option)" :value="String(option)">
              {{ pageSizeLabel(option) }}
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

      <div ref="gridScroll" class="grid-scroll">
        <div v-if="store.loading" class="skeleton" aria-label="Loading photos">
          <div class="skeleton-header" />
          <div class="skeleton-grid">
            <div v-for="i in 24" :key="i" class="skeleton-tile" />
          </div>
        </div>
        <div v-else-if="store.error" class="state state--error">
          <p>Can’t reach the library service</p>
          <code class="error-detail">{{ store.error }}</code>
          <button type="button" class="retry" @click="store.reload()">Retry</button>
        </div>
        <div v-else-if="store.total === 0 && store.hasActiveFilters" class="state">
          <p class="state-title">No photos match these filters</p>
          <button type="button" class="retry" @click="store.clearFilters()">
            Clear all filters
          </button>
        </div>
        <div v-else-if="store.total === 0" class="state">
          <p class="state-title">No photos indexed yet</p>
          <p class="state-sub">Add a folder and run a scan to build your library.</p>
          <RouterLink to="/scan" class="state-action">Run a scan</RouterLink>
        </div>
        <PhotoGrid v-else @open="store.openLightbox($event)" />
      </div>

      <SelectionBar />

      <footer
        v-if="!store.loading && !store.error && store.total > 0"
        class="pagination"
      >
        <span class="page-info">
          Showing {{ formatCount(store.pageStart) }}–{{ formatCount(store.pageEnd) }} of
          {{ formatCount(store.total) }}
        </span>
        <span class="spacer" />
        <template v-if="store.pageSize !== 'all' && store.totalPages > 1">
          <button
            type="button"
            class="page-btn"
            :disabled="store.page === 0"
            @click="withScrollReset(() => store.prevPage())"
          >
            ← Prev
          </button>
          <span class="page-indicator">
            Page {{ formatCount(store.page + 1) }} of {{ formatCount(store.totalPages) }}
          </span>
          <button
            type="button"
            class="page-btn"
            :disabled="store.page >= store.totalPages - 1"
            @click="withScrollReset(() => store.nextPage())"
          >
            Next →
          </button>
        </template>
      </footer>
    </section>

    <FilterPanel />
    <PhotoLightbox v-if="store.lightboxOpen" />
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

.breadcrumb-clear {
  border: 0;
  padding: 3px 8px;
  border-radius: 7px;
  background: var(--chip);
  color: var(--sub);
  font-size: 12px;
  cursor: pointer;
}

.breadcrumb-clear:hover {
  color: var(--fg);
}

.total {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}

.marked-link {
  font-size: 12px;
  font-weight: 500;
  text-decoration: none;
  color: var(--danger);
  padding: 3px 8px;
  border-radius: 7px;
  background: color-mix(in oklab, var(--danger) 10%, transparent);
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

.pagination {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 18px;
  background: var(--bar);
  border-top: 1px solid var(--border);
}

.page-info {
  font-size: 12px;
  color: var(--sub);
}

.page-indicator {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--muted);
}

.page-btn {
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--chip);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
}

.page-btn:disabled {
  opacity: 0.45;
  cursor: default;
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

.skeleton {
  padding: 18px;
}

.skeleton-header {
  width: 180px;
  height: 16px;
  border-radius: 5px;
  margin-bottom: 14px;
}

.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
  gap: 9px;
}

.skeleton-tile {
  aspect-ratio: 1;
  border-radius: 4px;
}

.skeleton-header,
.skeleton-tile {
  background: linear-gradient(
    100deg,
    var(--skeleton) 40%,
    var(--skeleton-hi) 50%,
    var(--skeleton) 60%
  );
  background-size: 200% 100%;
  animation: shimmer 1.4s linear infinite;
}

@keyframes shimmer {
  to {
    background-position: -200% 0;
  }
}

@media (max-width: 900px) {
  .sidebar {
    display: none;
  }
}
</style>
