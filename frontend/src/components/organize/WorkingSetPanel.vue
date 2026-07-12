<script setup lang="ts">
import { useOrganizeStore } from '@/stores/organize'
import { formatCount } from '@/utils/format'

const store = useOrganizeStore()

/** Deterministic muted tile gradient per folder name (as in the design's
 * working-set rows — a visual identity, not a palette token). */
function tileStyle(name: string): Record<string, string> {
  let hash = 0
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) % 360
  return {
    background: `linear-gradient(120deg, hsl(${hash} 22% 55%), hsl(${hash} 26% 40%))`,
  }
}
</script>

<template>
  <aside class="panel">
    <div class="head">
      <span class="label">WORKING SET</span>
      <span class="count">{{ store.workingSet.length }}</span>
    </div>
    <div class="rows">
      <div v-for="node in store.workingSet" :key="node.path" class="row">
        <div class="tile" :style="tileStyle(node.name)" aria-hidden="true" />
        <div class="meta">
          <div class="name" :title="node.path">{{ node.name }}</div>
          <div class="photos">{{ formatCount(node.photo_count) }} photos</div>
        </div>
        <button
          type="button"
          class="remove"
          :aria-label="`Remove ${node.name} from the working set`"
          @click="store.removeFolder(node.path)"
        >
          ×
        </button>
      </div>
      <p v-if="store.workingSet.length === 0" class="empty">
        Nothing selected yet. Check folders in the Library to build a working set.
      </p>
    </div>
    <RouterLink to="/library" class="add">+ Add folders</RouterLink>
  </aside>
</template>

<style scoped>
.panel {
  width: 296px;
  flex: none;
  display: flex;
  flex-direction: column;
  background: var(--sidebar);
  border-right: 1px solid var(--border);
}

.head {
  padding: 16px 16px 8px;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.label {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  margin-left: auto;
}

.rows {
  flex: 1;
  overflow: auto;
  padding: 0 10px;
}

.row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px;
  border-radius: 10px;
  margin-bottom: 3px;
}

.row:hover {
  background: var(--hover);
}

.tile {
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}

.meta {
  flex: 1;
  min-width: 0;
}

.name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.photos {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}

.remove {
  width: 22px;
  height: 22px;
  flex: none;
  border: 0;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: var(--muted);
  font-size: 15px;
  cursor: pointer;
}

.remove:hover {
  background: var(--hover);
  color: var(--fg);
}

.empty {
  padding: 10px;
  font-size: 12.5px;
  color: var(--sub);
  line-height: 1.5;
}

.add {
  flex: none;
  margin: 10px;
  height: 38px;
  border: 1px dashed var(--cb-border);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: var(--sub);
  font-size: 12.5px;
  font-weight: 600;
}

.add:hover {
  color: var(--fg);
  border-color: var(--muted);
}
</style>
