<script setup lang="ts">
import { computed } from 'vue'
import { useLibraryStore } from '@/stores/library'
import { formatCount } from '@/utils/format'
import type { FolderNode } from '@/api/folders'

const store = useLibraryStore()

const visibleRows = computed<FolderNode[]>(() => {
  const byPath = new Map(store.folders.map((node) => [node.path, node]))
  return store.folders.filter((node) => {
    let parent = node.parent_path
    while (parent) {
      if (!store.expanded.has(parent)) return false
      parent = byPath.get(parent)?.parent_path ?? null
    }
    return true
  })
})
</script>

<template>
  <div class="tree-wrap">
    <div class="scroll">
      <p class="label">LIBRARY</p>
      <div
        v-for="node in visibleRows"
        :key="node.path"
        class="row"
        :style="{ paddingLeft: `${12 + node.depth * 18}px` }"
        role="treeitem"
        :aria-expanded="node.has_children ? store.expanded.has(node.path) : undefined"
        :aria-selected="store.checkedFolders.has(node.path)"
        @click="store.toggleChecked(node.path)"
      >
        <span
          class="chevron"
          @click.stop="node.has_children && store.toggleExpanded(node.path)"
        >
          {{ node.has_children ? (store.expanded.has(node.path) ? '▾' : '▸') : '' }}
        </span>
        <span class="checkbox" :class="{ 'checkbox--on': store.checkedFolders.has(node.path) }">
          {{ store.checkedFolders.has(node.path) ? '✓' : '' }}
        </span>
        <span class="marker" aria-hidden="true" />
        <span class="name" :class="{ 'name--root': node.depth === 0 }">{{ node.name }}</span>
        <span class="count">{{ formatCount(node.photo_count) }}</span>
      </div>
      <p v-if="!store.folders.length" class="empty">No folders indexed yet.</p>
    </div>

    <div class="selection-card">
      <p class="selection-label">Selected for organizing</p>
      <p class="selection-totals">
        <strong>{{ store.checkedTotals.folders }}</strong> folders ·
        <strong>{{ formatCount(store.checkedTotals.photos) }}</strong> photos
      </p>
      <div class="selection-actions">
        <RouterLink to="/organize" class="btn btn--primary">Organize</RouterLink>
        <RouterLink to="/duplicates" class="btn">Find dupes</RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tree-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.scroll {
  flex: 1;
  overflow: auto;
  padding: 14px 10px 0;
}

.label {
  margin: 0;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--muted);
  padding: 0 8px 8px;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding-right: 8px;
  border-radius: 7px;
  cursor: pointer;
}

.row:hover {
  background: var(--hover);
}

.chevron {
  width: 14px;
  flex: none;
  color: var(--muted);
  font-size: 9px;
  text-align: center;
  cursor: pointer;
}

.checkbox {
  width: 15px;
  height: 15px;
  flex: none;
  border-radius: 4px;
  border: 1.5px solid var(--cb-border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--on-accent);
  font-size: 10px;
}

.checkbox--on {
  background: var(--accent);
  border-color: var(--accent);
}

.marker {
  width: 12px;
  height: 10px;
  flex: none;
  border-radius: 2px;
  background: var(--folder);
}

.name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.name--root {
  font-weight: 600;
}

.count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}

.empty {
  padding: 8px;
  color: var(--muted);
}

.selection-card {
  flex: none;
  margin: 10px;
  padding: 12px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.selection-label {
  margin: 0 0 4px;
  font-size: 11px;
  color: var(--sub);
}

.selection-totals {
  margin: 0 0 10px;
  font-size: 13px;
}

.selection-actions {
  display: flex;
  gap: 8px;
}

.btn {
  flex: 1;
  text-align: center;
  padding: 6px 0;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 500;
  text-decoration: none;
  color: var(--fg);
  background: var(--chip);
}

.btn--primary {
  background: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
}
</style>
