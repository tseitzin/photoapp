<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getPhoto, previewUrl, thumbnailUrl, type PhotoDetail } from '@/api/photos'
import { useLibraryStore } from '@/stores/library'
import { formatBytes, formatCount, formatDate } from '@/utils/format'

const store = useLibraryStore()

const detail = ref<PhotoDetail | null>(null)
const detailCache = new Map<number, PhotoDetail>()

// The cached 512px thumbnail shows instantly; the full 2048px preview is only
// requested after the user settles on a photo (debounced), so rapidly skimming
// fires no preview generations on the server. Neighbors are prefetched on settle.
const PREVIEW_DEBOUNCE_MS = 150
const previewSrc = ref<string | null>(null)
let previewTimer: ReturnType<typeof setTimeout> | undefined

function prefetchNeighborPreviews(): void {
  for (const delta of [1, -1]) {
    const neighbor = store.photos[store.lightboxIndex + delta]
    if (neighbor) new Image().src = previewUrl(neighbor.id)
  }
}

watch(
  () => store.lightboxPhoto?.id,
  (id) => {
    previewSrc.value = null // show the thumbnail while settling — no preview request
    clearTimeout(previewTimer)
    if (id == null) return
    previewTimer = setTimeout(() => {
      previewSrc.value = previewUrl(id)
      prefetchNeighborPreviews()
    }, PREVIEW_DEBOUNCE_MS)
  },
  { immediate: true },
)

function onPreviewLoad(event: Event): void {
  ;(event.target as HTMLImageElement).classList.add('loaded')
}

watch(
  () => store.lightboxPhoto?.id,
  async (id) => {
    detail.value = null
    if (id == null) return
    const cached = detailCache.get(id)
    if (cached) {
      detail.value = cached
      return
    }
    try {
      const loaded = await getPhoto(id)
      detailCache.set(id, loaded)
      if (store.lightboxPhoto?.id === id) detail.value = loaded
    } catch {
      /* metadata row degrades gracefully */
    }
  },
  { immediate: true },
)

const iso = computed(() => {
  const value = detail.value?.exif?.['ISOSpeedRatings']
  return typeof value === 'number' || typeof value === 'string' ? `ISO ${value}` : null
})

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') store.closeLightbox()
  else if (event.key === 'ArrowRight') store.lightboxStep(1)
  else if (event.key === 'ArrowLeft') store.lightboxStep(-1)
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(previewTimer)
})

// Filmstrip: a window around the current index keeps the DOM small.
const strip = computed(() => {
  const start = Math.max(0, store.lightboxIndex - 12)
  return store.photos.slice(start, store.lightboxIndex + 13).map((photo, offset) => ({
    photo,
    index: start + offset,
  }))
})

const stripEl = ref<HTMLElement | null>(null)
watch(
  () => store.lightboxIndex,
  () => {
    requestAnimationFrame(() => {
      const current = stripEl.value?.querySelector('.strip-thumb--current')
      current?.scrollIntoView?.({ inline: 'center', block: 'nearest' })
    })
  },
)
</script>

<template>
  <div v-if="store.lightboxPhoto" class="lightbox" role="dialog" aria-modal="true">
    <header class="bar">
      <span class="filename">{{ store.lightboxPhoto.filename }}</span>
      <span class="counter">
        {{ formatCount(store.lightboxIndex + 1) }} / {{ formatCount(store.total) }}
      </span>
      <span class="spacer" />
      <button
        type="button"
        class="mark-btn"
        :class="{ 'mark-btn--on': store.lightboxPhoto.marked_for_deletion }"
        :aria-pressed="store.lightboxPhoto.marked_for_deletion"
        @click="store.toggleMark(store.lightboxPhoto.id)"
      >
        🗑 {{ store.lightboxPhoto.marked_for_deletion ? 'Marked for deletion' : 'Mark for deletion' }}
      </button>
      <button type="button" class="icon-btn" aria-label="Close" @click="store.closeLightbox()">
        ×
      </button>
    </header>

    <div class="stage">
      <button
        type="button"
        class="nav nav--prev"
        aria-label="Previous photo"
        :disabled="store.lightboxIndex === 0"
        @click="store.lightboxStep(-1)"
      >
        ‹
      </button>
      <div
        class="image-wrap"
        :style="{ backgroundImage: `url(${thumbnailUrl(store.lightboxPhoto.id)})` }"
      >
        <img
          v-if="previewSrc"
          :key="store.lightboxPhoto.id"
          class="image"
          :src="previewSrc"
          :alt="store.lightboxPhoto.filename"
          @load="onPreviewLoad"
        />
      </div>
      <button
        type="button"
        class="nav nav--next"
        aria-label="Next photo"
        :disabled="store.lightboxIndex >= store.photos.length - 1"
        @click="store.lightboxStep(1)"
      >
        ›
      </button>
    </div>

    <p class="meta">
      <span v-if="store.lightboxPhoto.width">
        {{ store.lightboxPhoto.width }} × {{ store.lightboxPhoto.height }}
      </span>
      <span>{{ formatBytes(store.lightboxPhoto.size_bytes) }}</span>
      <span v-if="store.lightboxPhoto.camera_model">{{ store.lightboxPhoto.camera_model }}</span>
      <span v-if="iso">{{ iso }}</span>
      <span>{{ formatDate(store.lightboxPhoto.captured_at) }}</span>
    </p>

    <div ref="stripEl" class="strip">
      <button
        v-for="entry in strip"
        :key="entry.photo.id"
        type="button"
        class="strip-thumb"
        :class="{ 'strip-thumb--current': entry.index === store.lightboxIndex }"
        :aria-label="entry.photo.filename"
        @click="store.openLightbox(entry.photo.id)"
      >
        <img :src="thumbnailUrl(entry.photo.id)" :alt="''" loading="lazy" />
      </button>
    </div>
  </div>
</template>

<style scoped>
/* Dark regardless of theme, per the design. */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: rgba(9, 9, 11, 0.96);
  color: #e7e7ea;
  display: flex;
  flex-direction: column;
}

.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 18px;
}

.filename {
  font-family: var(--font-mono);
  font-size: 12.5px;
}

.counter {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: #8a8a92;
}

.spacer {
  flex: 1;
}

.icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid #3a3a41;
  background: transparent;
  color: inherit;
  font-size: 17px;
  cursor: pointer;
}

.mark-btn {
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid #3a3a41;
  background: transparent;
  color: #e7e7ea;
  font-size: 12.5px;
  cursor: pointer;
}

.mark-btn--on {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff;
}

.stage {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 0 18px;
}

.image-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
  height: 100%;
  max-width: calc(100% - 140px);
  display: flex;
  align-items: center;
  justify-content: center;
  /* Cached thumbnail shown instantly (upscaled); the full preview covers it. */
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
}

.image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 6px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  opacity: 0;
  transition: opacity 0.15s ease;
}

.image.loaded {
  opacity: 1;
}

.nav {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 50%;
  border: 1px solid #3a3a41;
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  font-size: 20px;
  cursor: pointer;
}

.nav:disabled {
  opacity: 0.3;
  cursor: default;
}

.meta {
  display: flex;
  justify-content: center;
  gap: 22px;
  margin: 12px 0 0;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: #8a8a92;
}

.strip {
  display: flex;
  gap: 6px;
  justify-content: safe center;
  overflow-x: auto;
  padding: 12px 18px 16px;
}

.strip-thumb {
  width: 64px;
  height: 64px;
  flex: none;
  padding: 0;
  border: 0;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  opacity: 0.6;
}

.strip-thumb--current {
  opacity: 1;
  box-shadow: 0 0 0 2px oklch(0.68 0.1 250);
}

.strip-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
</style>
