<script setup lang="ts">
import { computed } from 'vue'
import { thumbnailUrl } from '@/api/photos'
import { useLibraryStore } from '@/stores/library'
import { formatBytes, formatCount, formatDate } from '@/utils/format'

const store = useLibraryStore()

const metadataRows = computed(() => {
  const photo = store.selectedPhoto
  if (!photo) return []
  return [
    {
      key: 'Dimensions',
      value: photo.width && photo.height ? `${photo.width} × ${photo.height}` : '—',
    },
    { key: 'Size', value: formatBytes(photo.size_bytes) },
    { key: 'Format', value: photo.ext.toUpperCase() },
    { key: 'Camera', value: photo.camera_model ?? '—' },
    { key: 'Captured', value: formatDate(photo.captured_at) },
    { key: 'Folder', value: photo.path.slice(0, photo.path.lastIndexOf('/')) },
  ]
})
</script>

<template>
  <aside class="panel">
    <div class="scroll">
      <p class="label">FILTERS</p>

      <p class="group-title">File type</p>
      <div class="chips">
        <button
          v-for="facet in store.facets?.file_types ?? []"
          :key="facet.value"
          type="button"
          class="chip"
          :class="{ 'chip--on': store.filters.types.includes(facet.value) }"
          @click="store.toggleType(facet.value)"
        >
          {{ facet.value.toUpperCase() }}
          <span class="chip-count">{{ formatCount(facet.count) }}</span>
        </button>
        <p v-if="!store.facets?.file_types.length" class="muted">No photos yet</p>
      </div>

      <p class="group-title">Camera</p>
      <label
        v-for="facet in store.facets?.cameras ?? []"
        :key="facet.value"
        class="camera-row"
      >
        <input
          type="checkbox"
          class="camera-check"
          :checked="store.filters.cameras.includes(facet.value)"
          @change="store.toggleCamera(facet.value)"
        />
        <span class="camera-name">{{ facet.value }}</span>
        <span class="camera-count">{{ formatCount(facet.count) }}</span>
      </label>
      <p v-if="!store.facets?.cameras.length" class="muted">No camera metadata</p>

      <button
        v-if="store.hasActiveFilters"
        type="button"
        class="clear"
        @click="store.clearFilters()"
      >
        Clear all filters
      </button>

      <hr class="divider" />

      <p class="label">METADATA</p>
      <template v-if="store.selectedPhoto">
        <div class="preview">
          <img :src="thumbnailUrl(store.selectedPhoto.id)" :alt="store.selectedPhoto.filename" />
        </div>
        <p class="filename">{{ store.selectedPhoto.filename }}</p>
        <dl class="meta">
          <template v-for="row in metadataRows" :key="row.key">
            <dt>{{ row.key }}</dt>
            <dd>{{ row.value }}</dd>
          </template>
        </dl>
      </template>
      <p v-else class="muted">Select a photo to see its details.</p>
    </div>
  </aside>
</template>

<style scoped>
.panel {
  width: 302px;
  flex: none;
  background: var(--sidebar);
  border-left: 1px solid var(--border);
  min-height: 0;
  display: flex;
}

.scroll {
  flex: 1;
  overflow: auto;
  padding: 14px 16px 24px;
}

.label {
  margin: 0 0 10px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.group-title {
  margin: 12px 0 8px;
  font-size: 12px;
  color: var(--sub);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: var(--chip);
  color: var(--fg);
  font-size: 12px;
  cursor: pointer;
}

.chip:hover {
  background: var(--chip-hover);
}

.chip--on {
  background: var(--sel-chip-bg);
  color: var(--sel-chip-fg);
  border-color: var(--sel-chip-border);
}

.chip-count {
  font-family: var(--font-mono);
  font-size: 11px;
  opacity: 0.75;
}

.camera-row {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 28px;
  cursor: pointer;
}

.camera-check {
  accent-color: var(--accent);
  width: 15px;
  height: 15px;
}

.camera-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.camera-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}

.clear {
  margin-top: 12px;
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--fg);
  font-size: 12px;
  cursor: pointer;
}

.divider {
  border: 0;
  border-top: 1px solid var(--divider);
  margin: 16px 0;
}

.preview {
  aspect-ratio: 3 / 2;
  border-radius: 8px;
  overflow: hidden;
  background: var(--skeleton);
  margin-bottom: 8px;
}

.preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.filename {
  margin: 0 0 10px;
  font-family: var(--font-mono);
  font-size: 12px;
  word-break: break-all;
}

.meta {
  margin: 0;
  display: grid;
  grid-template-columns: 84px 1fr;
  row-gap: 7px;
  font-size: 12px;
}

.meta dt {
  color: var(--sub);
}

.meta dd {
  margin: 0;
  word-break: break-all;
}

.muted {
  color: var(--muted);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .panel {
    display: none;
  }
}
</style>
