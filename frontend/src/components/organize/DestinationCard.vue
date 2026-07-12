<script setup lang="ts">
import { computed } from 'vue'
import type { OrganizeMode } from '@/api/organize'
import { useOrganizeStore } from '@/stores/organize'

const store = useOrganizeStore()

const MODES: { value: OrganizeMode; label: string }[] = [
  { value: 'keep', label: 'Keep structure' },
  { value: 'date', label: 'By date' },
  { value: 'camera', label: 'By camera' },
]

const HELP: Record<OrganizeMode, string> = {
  keep: 'Photos keep their current folder names under the destination.',
  date: 'Photos are sorted into Year / Month folders by capture date; photos without one go to Undated/.',
  camera: 'Photos are grouped into a folder per camera model.',
}

const help = computed(() => HELP[store.mode])
</script>

<template>
  <section class="card">
    <h2 class="card-title">Destination</h2>
    <div class="path-row">
      <span class="folder-glyph" aria-hidden="true" />
      <span class="path" :title="store.destination">{{ store.destination || '—' }}</span>
      <button type="button" class="browse" @click="store.pickerOpen = true">Browse</button>
    </div>
    <div class="seg" role="radiogroup" aria-label="Destination structure">
      <button
        v-for="m in MODES"
        :key="m.value"
        type="button"
        class="seg-btn"
        :class="{ 'seg-btn--on': store.mode === m.value }"
        role="radio"
        :aria-checked="store.mode === m.value"
        @click="store.mode = m.value"
      >
        {{ m.label }}
      </button>
    </div>
    <p class="help">{{ help }}</p>
    <p v-if="store.preview?.destination_new_root" class="new-root-note">
      This folder isn’t in your library yet — it will be added automatically when you organize,
      so the moved photos stay visible.
    </p>
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  margin-bottom: 16px;
}

.card-title {
  margin: 0 0 14px;
  font-size: 14px;
  font-weight: 600;
}

.path-row {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 40px;
  padding: 0 6px 0 14px;
  background: var(--chip);
  border-radius: 10px;
  margin-bottom: 14px;
}

.folder-glyph {
  width: 13px;
  height: 11px;
  border-radius: 2px;
  background: var(--folder);
  flex: none;
}

.path {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 12.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.browse {
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 7px;
  background: var(--card);
  color: var(--fg);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-card);
}

.seg {
  display: flex;
  background: var(--seg-bg);
  border-radius: 9px;
  padding: 3px;
  gap: 3px;
  margin-bottom: 12px;
}

.seg-btn {
  flex: 1;
  text-align: center;
  padding: 7px 8px;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12.5px;
  background: transparent;
  color: var(--sub);
  font-weight: 500;
}

.seg-btn--on {
  background: var(--seg-active-bg);
  color: var(--seg-active-fg);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.help {
  margin: 0;
  font-size: 12px;
  color: var(--sub);
  line-height: 1.5;
}

.new-root-note {
  margin: 10px 0 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--success-soft);
  color: var(--success-fg);
  font-size: 12px;
  line-height: 1.5;
}
</style>
