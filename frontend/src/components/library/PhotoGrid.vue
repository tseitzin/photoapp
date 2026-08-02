<script setup lang="ts">
import PhotoTile from './PhotoTile.vue'
import { useLibraryStore } from '@/stores/library'
import { formatCount } from '@/utils/format'

const store = useLibraryStore()
const emit = defineEmits<{ open: [photoId: number] }>()

// Single click selects (details show in the right panel); shift extends the
// run from the last plain click, ⌘/Ctrl toggles one photo. Double-click opens
// the full-screen lightbox.
function onTileClick(photoId: number, event: MouseEvent): void {
  store.clickPhoto(photoId, {
    shift: event.shiftKey,
    toggle: event.metaKey || event.ctrlKey,
  })
}

function onTileOpen(photoId: number): void {
  store.selectPhoto(photoId)
  emit('open', photoId)
}
</script>

<template>
  <div class="grid-root">
    <section v-for="section in store.sections" :key="section.key" class="section">
      <header class="section-header">
        <h2 class="section-title">{{ section.title }}</h2>
        <span class="section-count">{{ formatCount(section.photos.length) }} photos</span>
        <span class="rule" aria-hidden="true" />
      </header>
      <div class="tiles">
        <PhotoTile
          v-for="photo in section.photos"
          :key="photo.id"
          :photo="photo"
          :selected="store.selectedIds.has(photo.id)"
          @select="onTileClick(photo.id, $event)"
          @open="onTileOpen(photo.id)"
          @mark="store.toggleMark(photo.id)"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.grid-root {
  padding: 0 18px 24px;
  /* Shift+click would otherwise drag a text selection across the grid. */
  user-select: none;
}

.section-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 18px 0 10px;
}

.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.section-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}

.rule {
  flex: 1;
  height: 1px;
  background: var(--divider);
}

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--tile-min, 112px), 1fr));
  gap: 9px;
}
</style>
