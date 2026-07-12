<script setup lang="ts">
import { computed, ref } from 'vue'
import { useLibraryStore } from '@/stores/library'
import { useOrganizeStore } from '@/stores/organize'

const library = useLibraryStore()
const store = useOrganizeStore()

const selected = ref<string>(store.destination)
const expanded = ref(new Set(library.folders.filter((n) => n.depth === 0).map((n) => n.path)))
const newFolderOpen = ref(false)
const newFolderName = ref('')
const newFolderError = ref<string | null>(null)

const visibleRows = computed(() =>
  library.folders.filter((node) => {
    let parent = node.parent_path
    while (parent) {
      if (!expanded.value.has(parent)) return false
      parent = library.folders.find((n) => n.path === parent)?.parent_path ?? null
    }
    return true
  }),
)

/** The path Choose will commit: the selected folder plus an optional new segment. */
const chosenPath = computed(() => {
  const base = selected.value
  const segment = newFolderName.value.trim()
  return newFolderOpen.value && segment ? `${base}/${segment}` : base
})

function toggleExpanded(path: string, event: Event): void {
  event.stopPropagation()
  const next = new Set(expanded.value)
  if (!next.delete(path)) next.add(path)
  expanded.value = next
}

function validSegment(segment: string): string | null {
  if (!segment) return 'Folder name is required'
  if (segment.includes('/')) return 'Folder names cannot contain “/”'
  if (segment.startsWith('.')) return 'Folder names cannot start with “.”'
  return null
}

function choose(): void {
  if (newFolderOpen.value) {
    const problem = validSegment(newFolderName.value.trim())
    if (problem) {
      newFolderError.value = problem
      return
    }
  }
  if (!selected.value) return
  store.destination = chosenPath.value
  store.pickerOpen = false
}
</script>

<template>
  <div class="backdrop" @click.self="store.pickerOpen = false">
    <div class="modal" role="dialog" aria-modal="true" aria-label="Choose destination">
      <header class="head">
        <h2 class="title">Choose destination</h2>
        <p class="sub">Pick the folder your organized photos will move into.</p>
      </header>

      <div class="tree">
        <div
          v-for="node in visibleRows"
          :key="node.path"
          class="node"
          :class="{ 'node--selected': node.path === selected }"
          :style="{ paddingLeft: `${12 + node.depth * 20}px` }"
          @click="selected = node.path"
        >
          <button
            v-if="node.has_children"
            type="button"
            class="chev"
            :aria-label="`Toggle ${node.name}`"
            @click="toggleExpanded(node.path, $event)"
          >
            {{ expanded.has(node.path) ? '▾' : '▸' }}
          </button>
          <span v-else class="chev-spacer" />
          <span class="folder-glyph" aria-hidden="true" />
          <span class="node-name">{{ node.name }}</span>
        </div>
        <p v-if="visibleRows.length === 0" class="empty">
          No indexed folders yet — run a scan first.
        </p>
      </div>

      <footer class="foot">
        <button type="button" class="new-folder" @click="newFolderOpen = !newFolderOpen">
          <span aria-hidden="true">+</span> New folder
        </button>
        <input
          v-if="newFolderOpen"
          v-model="newFolderName"
          class="new-input"
          type="text"
          placeholder="Folder name"
          aria-label="New folder name"
          @input="newFolderError = null"
          @keydown.enter.prevent="choose"
        />
        <span class="sel-path" :title="chosenPath">{{ chosenPath }}</span>
        <button type="button" class="cancel" @click="store.pickerOpen = false">Cancel</button>
        <button type="button" class="choose" :disabled="!selected" @click="choose">Choose</button>
      </footer>
      <p v-if="newFolderError" class="error" role="alert">{{ newFolderError }}</p>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(9, 9, 11, 0.5);
}

.modal {
  width: 520px;
  max-width: 92vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: var(--shadow-modal);
}

.head {
  flex: none;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border);
}

.title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.sub {
  margin: 3px 0 0;
  font-size: 12.5px;
  color: var(--sub);
}

.tree {
  flex: 1;
  overflow: auto;
  padding: 10px;
  min-height: 120px;
}

.node {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 36px;
  padding-right: 12px;
  border-radius: 9px;
  cursor: pointer;
}

.node--selected {
  background: var(--sel-chip-bg);
  color: var(--sel-chip-fg);
}

.chev {
  width: 14px;
  flex: none;
  border: 0;
  background: transparent;
  text-align: center;
  font-size: 9px;
  color: var(--muted);
  cursor: pointer;
  padding: 0;
}

.chev-spacer {
  width: 14px;
  flex: none;
}

.folder-glyph {
  width: 15px;
  height: 12px;
  flex: none;
  border-radius: 3px;
  background: var(--folder);
}

.node-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.empty {
  padding: 12px;
  font-size: 12.5px;
  color: var(--sub);
}

.foot {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
}

.new-folder {
  height: 36px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 13px;
  border: 0;
  border-radius: 9px;
  background: var(--chip);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.new-input {
  height: 36px;
  width: 130px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--card);
  color: var(--fg);
  font-size: 12.5px;
}

.sel-path {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cancel {
  height: 36px;
  padding: 0 16px;
  border: 0;
  border-radius: 9px;
  background: var(--chip);
  color: var(--fg);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.choose {
  height: 36px;
  padding: 0 18px;
  border: 0;
  border-radius: 9px;
  background: var(--accent);
  color: var(--on-accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.choose:disabled {
  opacity: 0.45;
  cursor: default;
}

.error {
  margin: 0;
  padding: 0 20px 14px;
  font-size: 12px;
  color: var(--danger);
}
</style>
