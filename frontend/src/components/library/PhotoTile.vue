<script setup lang="ts">
import { thumbnailUrl } from '@/api/photos'
import type { PhotoRead } from '@/api/photos'

/**
 * One grid tile.
 *
 * Split out of PhotoGrid so Vue can bail out per tile: with the tiles as plain
 * elements in the grid's own render scope, reading selection state re-diffed
 * every tile in the library on each click. As a child with `selected` as a
 * prop, only the tiles whose props actually changed re-render.
 *
 * For the same reason the tile — not the grid — reads `marked_for_deletion`,
 * so flagging one photo re-renders one tile.
 */
const props = defineProps<{ photo: PhotoRead; selected: boolean }>()

const emit = defineEmits<{
  select: [event: MouseEvent]
  open: []
  mark: []
}>()
</script>

<template>
  <div class="tile" :class="{ 'tile--selected': props.selected, 'tile--marked': props.photo.marked_for_deletion }">
    <button
      type="button"
      class="tile-img"
      :aria-label="props.photo.filename"
      :aria-pressed="props.selected"
      :title="`${props.photo.filename} — double-click to open`"
      @click="emit('select', $event)"
      @dblclick="emit('open')"
    >
      <img :src="thumbnailUrl(props.photo.id)" :alt="props.photo.filename" loading="lazy" />
    </button>
    <!-- The marked ring overrides the selected ring, so selection needs a
         badge of its own to stay visible on a flagged photo. -->
    <span v-if="props.selected" class="select-badge" aria-hidden="true">✓</span>
    <button
      type="button"
      class="mark-toggle"
      :class="{ 'mark-toggle--on': props.photo.marked_for_deletion }"
      :aria-pressed="props.photo.marked_for_deletion"
      :aria-label="
        props.photo.marked_for_deletion
          ? `Unmark ${props.photo.filename}`
          : `Mark ${props.photo.filename} for deletion`
      "
      :title="props.photo.marked_for_deletion ? 'Marked for deletion' : 'Mark for deletion'"
      @click.stop="emit('mark')"
    >
      🗑
    </button>
  </div>
</template>

<style scoped>
.tile {
  position: relative;
  aspect-ratio: 1;
  border-radius: 4px;
  overflow: hidden;
  background: var(--skeleton);
  content-visibility: auto;
  /* `auto` lets the browser keep the real measured size once a tile has been
     rendered; the fallback is only the first-paint estimate. Using --tile-min
     alone under-reserved height, because `1fr` tracks are wider than the min. */
  contain-intrinsic-size: auto var(--tile-min, 112px);
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
