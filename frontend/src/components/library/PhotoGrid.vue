<script setup lang="ts">
import { thumbnailUrl } from '@/api/photos'
import { useLibraryStore } from '@/stores/library'
import { formatCount } from '@/utils/format'

const store = useLibraryStore()
const emit = defineEmits<{ open: [photoId: number] }>()

// Single click selects (details show in the right panel); double-click opens
// the full-screen lightbox.
function onTileSelect(photoId: number): void {
  store.selectPhoto(photoId)
}

function onTileOpen(photoId: number): void {
  store.selectPhoto(photoId)
  emit('open', photoId)
}
</script>

<template>
  <div class="grid-root" :style="{ '--tile-min': `${store.tileSize}px` }">
    <section v-for="section in store.sections" :key="section.key" class="section">
      <header class="section-header">
        <h2 class="section-title">{{ section.title }}</h2>
        <span class="section-count">{{ formatCount(section.photos.length) }} photos</span>
        <span class="rule" aria-hidden="true" />
      </header>
      <div class="tiles">
        <button
          v-for="photo in section.photos"
          :key="photo.id"
          type="button"
          class="tile"
          :class="{ 'tile--selected': photo.id === store.selectedPhotoId }"
          :aria-label="photo.filename"
          :title="`${photo.filename} — double-click to open`"
          @click="onTileSelect(photo.id)"
          @dblclick="onTileOpen(photo.id)"
        >
          <img :src="thumbnailUrl(photo.id)" :alt="photo.filename" loading="lazy" />
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.grid-root {
  padding: 0 18px 24px;
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

.tile {
  aspect-ratio: 1;
  padding: 0;
  border: 0;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  background: var(--skeleton);
  content-visibility: auto;
  contain-intrinsic-size: var(--tile-min, 112px);
}

.tile:hover {
  box-shadow: 0 5px 14px rgba(0, 0, 0, 0.28);
}

.tile--selected {
  box-shadow: inset 0 0 0 3px var(--accent);
}

.tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.tile--selected img {
  /* keep the inset ring visible above the image */
  mix-blend-mode: normal;
  opacity: 0.92;
}
</style>
