<script setup lang="ts">
import { computed, onMounted, ref, watchEffect } from 'vue'
import { thumbnailUrl } from '@/api/photos'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { useQuarantineStore } from '@/stores/quarantine'
import { formatBytes, formatCount } from '@/utils/format'

const store = useQuarantineStore()

onMounted(() => void store.load())

const confirmingRemoval = ref(false)
const confirmingDelete = ref(false)
const selected = ref(new Set<number>())

const allSelected = computed(
  () =>
    store.quarantined.length > 0 && store.quarantined.every((photo) => selected.value.has(photo.id)),
)

// Drive the native indeterminate state (only some rows selected).
const selectAllEl = ref<HTMLInputElement | null>(null)
watchEffect(() => {
  if (!selectAllEl.value) return
  const chosen = store.quarantined.filter((photo) => selected.value.has(photo.id)).length
  selectAllEl.value.indeterminate = chosen > 0 && chosen < store.quarantined.length
})

function toggleSelectAll(): void {
  selected.value = allSelected.value
    ? new Set()
    : new Set(store.quarantined.map((photo) => photo.id))
}

const markedBytes = computed(() =>
  store.marked.reduce((sum, photo) => sum + photo.size_bytes, 0),
)
const selectedBytes = computed(() =>
  store.quarantined
    .filter((photo) => selected.value.has(photo.id))
    .reduce((sum, photo) => sum + photo.size_bytes, 0),
)

function toggleSelected(id: number): void {
  const next = new Set(selected.value)
  if (!next.delete(id)) next.add(id)
  selected.value = next
}

async function confirmRemoval(): Promise<void> {
  confirmingRemoval.value = false
  await store.applyRemovals(false)
}

async function confirmForce(): Promise<void> {
  store.clearForceWarning()
  await store.applyRemovals(true)
}

async function confirmDelete(): Promise<void> {
  confirmingDelete.value = false
  await store.deletePermanently([...selected.value])
  selected.value = new Set()
}

async function restoreSelected(): Promise<void> {
  await store.restore([...selected.value])
  selected.value = new Set()
}

function opLabel(op: string): string {
  return { quarantine: 'Quarantined', restore: 'Restored', delete: 'Deleted' }[op] ?? op
}
</script>

<template>
  <div class="quarantine">
    <h1 class="title">File management</h1>
    <p class="intro">
      Removal is quarantine-first: files move to
      <code class="mono">~/.aperture/quarantine</code> and can be restored until you
      permanently delete them. Every operation is recorded below.
    </p>

    <p v-if="store.error" class="error" role="alert">{{ store.error }}</p>
    <p
      v-if="store.lastBatch"
      class="notice"
      :class="{ 'notice--warn': store.lastBatch.failed > 0 }"
    >
      Last batch: {{ store.lastBatch.succeeded }} succeeded, {{ store.lastBatch.failed }} failed.
      <template v-if="store.lastBatch.failed > 0">
        {{store.lastBatch.results.filter((r) => !r.ok).map((r) => r.error).join(' · ')}}
      </template>
    </p>

    <!-- Marked for removal -->
    <section class="card">
      <header class="card-head">
        <h2 class="card-title">Marked for removal</h2>
        <span class="muted">
          {{ formatCount(store.marked.length) }} photos · {{ formatBytes(markedBytes) }}
        </span>
        <button
          type="button"
          class="btn btn--primary"
          :disabled="!store.marked.length"
          @click="confirmingRemoval = true"
        >
          Quarantine {{ formatCount(store.marked.length) }} photos…
        </button>
      </header>
      <p v-if="!store.marked.length" class="muted">
        Nothing marked. Mark photos for deletion from the Library (or review
        duplicates) and they’ll appear here.
      </p>
      <ul v-else class="rows">
        <li v-for="photo in store.marked" :key="photo.id" class="row">
          <img :src="thumbnailUrl(photo.id)" :alt="photo.filename" class="row-thumb" />
          <div class="row-body">
            <span class="row-name">{{ photo.filename }}</span>
            <span class="row-path">{{ photo.path }}</span>
          </div>
          <span class="row-meta">
            {{ photo.width }} × {{ photo.height }} · {{ formatBytes(photo.size_bytes) }}
          </span>
        </li>
      </ul>
    </section>

    <!-- In quarantine -->
    <section class="card">
      <header class="card-head">
        <h2 class="card-title">In quarantine</h2>
        <span class="muted">{{ formatCount(store.quarantinedTotal) }} photos</span>
        <label v-if="store.quarantined.length" class="select-all">
          <input
            ref="selectAllEl"
            type="checkbox"
            class="row-check"
            :checked="allSelected"
            aria-label="Select all quarantined photos"
            @change="toggleSelectAll"
          />
          Select all
        </label>
        <button
          type="button"
          class="btn"
          :disabled="!selected.size"
          @click="restoreSelected"
        >
          Restore selected ({{ selected.size }})
        </button>
        <button
          type="button"
          class="btn btn--danger"
          :disabled="!selected.size"
          @click="confirmingDelete = true"
        >
          Delete permanently…
        </button>
      </header>
      <p v-if="!store.quarantined.length" class="muted">Quarantine is empty.</p>
      <ul v-else class="rows">
        <li v-for="photo in store.quarantined" :key="photo.id" class="row row--selectable">
          <input
            type="checkbox"
            class="row-check"
            :checked="selected.has(photo.id)"
            :aria-label="`Select ${photo.filename}`"
            @change="toggleSelected(photo.id)"
          />
          <img :src="thumbnailUrl(photo.id)" :alt="photo.filename" class="row-thumb" />
          <div class="row-body">
            <span class="row-name">{{ photo.filename }}</span>
            <span class="row-path">was {{ photo.path }}</span>
          </div>
          <span class="row-meta">{{ formatBytes(photo.size_bytes) }}</span>
        </li>
      </ul>
    </section>

    <!-- Audit log -->
    <section class="card">
      <header class="card-head">
        <h2 class="card-title">History</h2>
        <span class="muted">{{ formatCount(store.operationsTotal) }} operations</span>
      </header>
      <p v-if="!store.operations.length" class="muted">No file operations yet.</p>
      <table v-else class="audit">
        <tbody>
          <tr v-for="op in store.operations" :key="op.id">
            <td class="audit-op" :class="`audit-op--${op.op}`">{{ opLabel(op.op) }}</td>
            <td class="audit-path">{{ op.src_path }}</td>
            <td class="audit-when">{{ new Date(op.performed_at).toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Dialogs -->
    <ConfirmDialog
      v-if="confirmingRemoval"
      title="Quarantine marked photos?"
      :confirm-label="`Quarantine ${store.marked.length} photos`"
      @confirm="confirmRemoval"
      @cancel="confirmingRemoval = false"
    >
      <p>
        {{ formatCount(store.marked.length) }} photos ({{ formatBytes(markedBytes) }}) will move
        to the quarantine folder. Originals leave your library but nothing is deleted — you can
        restore them at any time.
      </p>
      <ul class="dialog-list">
        <li v-for="photo in store.marked.slice(0, 12)" :key="photo.id">
          <span class="mono">{{ photo.path }}</span>
        </li>
        <li v-if="store.marked.length > 12" class="muted">
          … and {{ store.marked.length - 12 }} more
        </li>
      </ul>
    </ConfirmDialog>

    <ConfirmDialog
      v-if="store.forceWarning"
      title="This empties entire duplicate groups"
      confirm-label="Quarantine anyway"
      danger
      @confirm="confirmForce"
      @cancel="store.clearForceWarning()"
    >
      <p>
        <strong>Warning:</strong> {{ store.forceWarning }}
      </p>
      <p>
        Every copy of those photos would leave your library — no version remains. Are you sure?
      </p>
    </ConfirmDialog>

    <ConfirmDialog
      v-if="confirmingDelete"
      title="Permanently delete from quarantine?"
      :confirm-label="`Delete ${selected.size} photos forever`"
      danger
      type-to-confirm="DELETE"
      @confirm="confirmDelete"
      @cancel="confirmingDelete = false"
    >
      <p>
        {{ selected.size }} photos ({{ formatBytes(selectedBytes) }}) will be deleted from disk.
        <strong>This cannot be undone.</strong>
      </p>
    </ConfirmDialog>
  </div>
</template>

<style scoped>
.quarantine {
  max-width: 880px;
  width: 100%;
  margin: 0 auto;
  padding: 30px 32px 48px;
}

.title {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.intro {
  margin: 0 0 18px;
  color: var(--sub);
  font-size: 12.5px;
}

.mono {
  font-family: var(--font-mono);
  font-size: 11.5px;
}

.error {
  padding: 9px 12px;
  border-radius: 8px;
  background: color-mix(in oklab, var(--danger) 12%, var(--card));
  font-size: 12.5px;
}

.notice {
  padding: 9px 12px;
  border-radius: 8px;
  background: color-mix(in oklab, var(--success) 12%, var(--card));
  font-size: 12.5px;
  margin-bottom: 14px;
}

.notice--warn {
  background: color-mix(in oklab, var(--danger) 10%, var(--card));
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 18px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-card);
}

.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.card-title {
  flex: 1;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.muted {
  color: var(--muted);
  font-size: 12px;
}

.select-all {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--sub);
  cursor: pointer;
}

.btn {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--chip);
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
}

.btn--primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
}

.btn--danger {
  background: transparent;
  border-color: var(--danger);
  color: var(--danger);
  font-weight: 600;
}

.btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 320px;
  overflow: auto;
}

.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  border-top: 1px solid var(--divider);
}

.row-check {
  accent-color: var(--accent);
  width: 15px;
  height: 15px;
}

.row-thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 4px;
  background: var(--skeleton);
}

.row-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.row-name {
  font-size: 12.5px;
  font-weight: 500;
}

.row-path {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-meta {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--sub);
  white-space: nowrap;
}

.audit {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.audit td {
  padding: 6px 8px;
  border-top: 1px solid var(--divider);
}

.audit-op {
  font-weight: 600;
  white-space: nowrap;
}

.audit-op--quarantine {
  color: var(--accent);
}

.audit-op--restore {
  color: var(--success);
}

.audit-op--delete {
  color: var(--danger);
}

.audit-path {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--sub);
  word-break: break-all;
}

.audit-when {
  white-space: nowrap;
  color: var(--muted);
}

.dialog-list {
  margin: 10px 0 0;
  padding-left: 18px;
  max-height: 180px;
  overflow: auto;
}
</style>
