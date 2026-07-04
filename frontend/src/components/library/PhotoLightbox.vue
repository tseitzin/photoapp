<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getPhoto, previewUrl, thumbnailUrl, type PhotoDetail } from '@/api/photos'
import { useLibraryStore } from '@/stores/library'
import { formatBytes, formatCount, formatDate } from '@/utils/format'

const store = useLibraryStore()

const detail = ref<PhotoDetail | null>(null)
const detailCache = new Map<number, PhotoDetail>()

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
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

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
      stripEl.value
        ?.querySelector('.strip-thumb--current')
        ?.scrollIntoView({ inline: 'center', block: 'nearest' })
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
      <img
        :key="store.lightboxPhoto.id"
        class="image"
        :src="previewUrl(store.lightboxPhoto.id)"
        :alt="store.lightboxPhoto.filename"
      />
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

.stage {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 0 18px;
}

.image {
  max-width: calc(100% - 140px);
  max-height: 100%;
  object-fit: contain;
  border-radius: 6px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
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
