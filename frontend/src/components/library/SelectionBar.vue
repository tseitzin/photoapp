<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useLibraryStore } from '@/stores/library'
import { formatCount } from '@/utils/format'

const store = useLibraryStore()

const count = computed(() => store.selectedIds.size)
const busy = computed(() => store.loading)

// Escape is the conventional "never mind" for a selection. The lightbox owns
// the key while it is open, so stand down then.
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && !store.lightboxOpen) store.clearSelection()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div v-if="count > 0" class="selection-bar" role="toolbar" aria-label="Selected photos">
    <span class="count">{{ formatCount(count) }} selected</span>
    <span class="hint">Shift+click for a range · ⌘/Ctrl+click for one</span>
    <span class="spacer" />
    <button type="button" class="btn btn--danger" :disabled="busy" @click="store.setMarkedForSelection(true)">
      🗑 Mark for deletion
    </button>
    <button type="button" class="btn" :disabled="busy" @click="store.setMarkedForSelection(false)">
      ↺ Unmark
    </button>
    <button type="button" class="btn clear" @click="store.clearSelection()">✕ Clear</button>
  </div>
</template>

<style scoped>
.selection-bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 18px;
  background: var(--bar);
  border-top: 1px solid var(--border);
}

.count {
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  color: var(--accent);
}

.hint {
  font-size: 11.5px;
  color: var(--muted);
}

.spacer {
  flex: 1;
}

.btn {
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--chip);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
}

.btn:hover:not(:disabled) {
  background: var(--chip-hover);
}

.btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.btn--danger {
  border-color: transparent;
  background: var(--danger);
  color: #fff;
}

.btn--danger:hover:not(:disabled) {
  background: var(--danger);
  filter: brightness(1.08);
}

@media (max-width: 900px) {
  .hint {
    display: none;
  }
}
</style>
