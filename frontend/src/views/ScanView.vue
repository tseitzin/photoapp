<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useScanStore } from '@/stores/scan'
import { formatCount } from '@/utils/format'

const store = useScanStore()
const newRootPath = ref('')
const addingRoot = ref(false)

onMounted(() => void store.load())

async function submitRoot(): Promise<void> {
  const path = newRootPath.value.trim()
  if (!path) return
  if (await store.addRoot(path)) {
    newRootPath.value = ''
    addingRoot.value = false
  }
}
</script>

<template>
  <div class="scan">
    <!-- Phase: setup -->
    <template v-if="store.phase === 'setup'">
      <h1 class="title">Index your photo library</h1>
      <p class="intro">
        Aperture scans the folders you approve, in place — your files are never moved or
        modified. Rescans only touch what changed.
      </p>

      <p v-if="store.error" class="error" role="alert">{{ store.error }}</p>

      <section class="card">
        <p class="card-label">SOURCES</p>
        <label v-for="root in store.roots" :key="root.id" class="source-row">
          <input
            type="checkbox"
            class="source-check"
            :checked="store.selectedRootIds.has(root.id)"
            @change="store.toggleRoot(root.id)"
          />
          <span class="source-icon" aria-hidden="true">▤</span>
          <span class="source-path">{{ root.path }}</span>
          <button
            type="button"
            class="source-remove"
            :aria-label="`Remove ${root.path}`"
            @click.prevent="store.removeRoot(root.id)"
          >
            ×
          </button>
        </label>
        <p v-if="!store.roots.length" class="muted">No folders configured yet.</p>

        <form v-if="addingRoot" class="add-form" @submit.prevent="submitRoot">
          <input
            v-model="newRootPath"
            class="add-input"
            type="text"
            placeholder="/Users/tim/Pictures"
            aria-label="Absolute folder path"
          />
          <button type="submit" class="btn btn--primary">Add</button>
          <button type="button" class="btn" @click="addingRoot = false">Cancel</button>
        </form>
        <button v-else type="button" class="add-toggle" @click="addingRoot = true">
          + Add a folder
        </button>
      </section>

      <div class="start-row">
        <button
          type="button"
          class="btn btn--primary btn--lg"
          :disabled="store.selectedRootIds.size === 0"
          @click="store.start()"
        >
          Start scan
        </button>
        <span class="muted">
          {{ store.selectedRootIds.size }} of {{ store.roots.length }} sources selected ·
          subfolders included
        </span>
      </div>
    </template>

    <!-- Phase: scanning -->
    <template v-else-if="store.phase === 'scanning'">
      <div class="spinner" aria-hidden="true" />
      <h1 class="title">Scanning your library…</h1>
      <p class="current-path">{{ store.activeScan?.current_path ?? 'Discovering files…' }}</p>

      <div class="progress-track">
        <div class="progress-fill" :style="{ width: `${store.progressPct}%` }" />
      </div>
      <p class="muted">
        {{ formatCount(store.activeScan?.files_processed ?? 0) }} of
        {{ formatCount(store.activeScan?.files_found ?? 0) }} files processed ·
        {{ store.progressPct }}%
      </p>

      <div class="tiles">
        <div class="tile">
          <p class="tile-label">FOUND</p>
          <p class="tile-value">{{ formatCount(store.activeScan?.files_found ?? 0) }}</p>
        </div>
        <div class="tile">
          <p class="tile-label">ADDED</p>
          <p class="tile-value">{{ formatCount(store.activeScan?.files_added ?? 0) }}</p>
        </div>
        <div class="tile">
          <p class="tile-label">UNCHANGED</p>
          <p class="tile-value">{{ formatCount(store.activeScan?.files_unchanged ?? 0) }}</p>
        </div>
        <div class="tile">
          <p class="tile-label">ERRORS</p>
          <p class="tile-value">{{ formatCount(store.activeScan?.error_count ?? 0) }}</p>
        </div>
      </div>

      <button type="button" class="btn" @click="store.cancel()">Cancel</button>
    </template>

    <!-- Phase: done -->
    <template v-else>
      <div class="check" aria-hidden="true">✓</div>
      <h1 class="title">Your library is ready</h1>
      <p class="intro">
        Indexed {{ formatCount(store.activeScan?.files_found ?? 0) }} photos —
        {{ formatCount(store.activeScan?.files_added ?? 0) }} new,
        {{ formatCount(store.activeScan?.files_changed ?? 0) }} changed,
        {{ formatCount(store.activeScan?.files_moved ?? 0) }} moved,
        {{ formatCount(store.activeScan?.files_missing ?? 0) }} missing,
        {{ formatCount(store.activeScan?.error_count ?? 0) }} errors.
      </p>
      <div class="done-actions">
        <RouterLink to="/library" class="btn btn--primary btn--lg">Open library →</RouterLink>
        <RouterLink to="/duplicates" class="btn btn--lg">Review duplicates</RouterLink>
        <button type="button" class="btn btn--lg" @click="store.reset()">Scan again</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.scan {
  max-width: 640px;
  width: 100%;
  margin: 0 auto;
  padding: 44px 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.title {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.intro {
  margin: 0 0 22px;
  color: var(--sub);
  line-height: 1.5;
}

.error {
  width: 100%;
  margin: 0 0 14px;
  padding: 9px 12px;
  border-radius: 8px;
  background: color-mix(in oklab, var(--danger) 12%, var(--card));
  color: var(--fg);
  font-size: 12.5px;
}

.card {
  width: 100%;
  text-align: left;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 18px;
  box-shadow: var(--shadow-card);
}

.card-label {
  margin: 0 0 10px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.source-row {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 38px;
  cursor: pointer;
}

.source-check {
  accent-color: var(--accent);
  width: 15px;
  height: 15px;
}

.source-icon {
  color: var(--muted);
}

.source-path {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-remove {
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 15px;
  cursor: pointer;
}

.source-remove:hover {
  color: var(--danger);
}

.add-toggle {
  margin-top: 8px;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 4px 0;
}

.add-form {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.add-input {
  flex: 1;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--app-bg);
  color: var(--fg);
  font-family: var(--font-mono);
  font-size: 12px;
}

.start-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 22px;
}

.btn {
  padding: 7px 16px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--chip);
  color: var(--fg);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}

.btn--primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
}

.btn--primary:disabled {
  opacity: 0.5;
  cursor: default;
}

.btn--lg {
  padding: 9px 22px;
}

.muted {
  color: var(--muted);
  font-size: 12.5px;
}

.spinner {
  width: 34px;
  height: 34px;
  margin: 26px 0 18px;
  border-radius: 50%;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.current-path {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--muted);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0 0 18px;
}

.progress-track {
  width: 100%;
  height: 8px;
  border-radius: 5px;
  background: var(--chip);
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.12s linear;
}

.tiles {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  width: 100%;
  margin: 22px 0;
}

.tile {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
}

.tile-label {
  margin: 0 0 4px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.tile-value {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 700;
}

.check {
  width: 52px;
  height: 52px;
  margin: 26px 0 16px;
  border-radius: 50%;
  background: var(--success);
  color: #fff;
  font-size: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.done-actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
  flex-wrap: wrap;
  justify-content: center;
}

@media (max-width: 600px) {
  .tiles {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
