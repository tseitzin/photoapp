<script setup lang="ts">
import { thumbnailUrl } from '@/api/photos'
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
  <div class="grid-root" :style="{ '--tile-min': `${store.tileSize}px` }">
    <section v-for="section in store.sections" :key="section.key" class="section">
      <header class="section-header">
        <h2 class="section-title">{{ section.title }}</h2>
        <span class="section-count">{{ formatCount(section.photos.length) }} photos</span>
        <span class="rule" aria-hidden="true" />
      </header>
      <div class="tiles">
        <div
          v-for="photo in section.photos"
          :key="photo.id"
          class="tile"
          :class="{
            'tile--selected': store.selectedIds.has(photo.id),
            'tile--marked': photo.marked_for_deletion,
          }"
        >
          <button
            type="button"
            class="tile-img"
            :aria-label="photo.filename"
            :aria-pressed="store.selectedIds.has(photo.id)"
            :title="`${photo.filename} — double-click to open`"
            @click="onTileClick(photo.id, $event)"
            @dblclick="onTileOpen(photo.id)"
          >
            <img :src="thumbnailUrl(photo.id)" :alt="photo.filename" loading="lazy" />
          </button>
          <!-- The marked ring overrides the selected ring, so selection needs
               a badge of its own to stay visible on a flagged photo. -->
          <span v-if="store.selectedIds.has(photo.id)" class="select-badge" aria-hidden="true">
            ✓
          </span>
          <button
            type="button"
            class="mark-toggle"
            :class="{ 'mark-toggle--on': photo.marked_for_deletion }"
            :aria-pressed="photo.marked_for_deletion"
            :aria-label="
              photo.marked_for_deletion
                ? `Unmark ${photo.filename}`
                : `Mark ${photo.filename} for deletion`
            "
            :title="photo.marked_for_deletion ? 'Marked for deletion' : 'Mark for deletion'"
            @click.stop="store.toggleMark(photo.id)"
          >
            🗑
          </button>
        </div>
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

.tile {
  position: relative;
  aspect-ratio: 1;
  border-radius: 4px;
  overflow: hidden;
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

/* Marked wins visually so flagged photos stand out while scrolling. */
.tile--marked {
  box-shadow: inset 0 0 0 3px var(--danger);
}

.tile-img {
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  display: block;
}

.tile-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.tile--marked .tile-img img {
  opacity: 0.6;
}

.select-badge {
  position: absolute;
  top: 5px;
  left: 5px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent);
  color: var(--on-accent);
  font-size: 11px;
  line-height: 18px;
  text-align: center;
  pointer-events: none;
}

.mark-toggle {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 50%;
  background: rgba(9, 9, 11, 0.55);
  color: #fff;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s;
}

.tile:hover .mark-toggle,
.mark-toggle:focus-visible {
  opacity: 1;
}

.mark-toggle--on {
  opacity: 1;
  background: var(--danger);
}
</style>
