<script setup lang="ts">
import { computed } from 'vue'
import { useOrganizeStore } from '@/stores/organize'
import { formatBytes, formatCount } from '@/utils/format'

const store = useOrganizeStore()

/** Split an example path so the destination prefix reads bold, per design. */
const examples = computed(() => {
  const dest = store.destination
  return (store.preview?.example_paths ?? []).map((path) => ({
    path,
    leaf: path.startsWith(dest) ? dest : '',
    rest: path.startsWith(dest) ? path.slice(dest.length) : path,
  }))
})

const summary = computed(() => {
  const p = store.preview
  if (!p) return []
  const rows = [
    { k: 'Photos moved', v: formatCount(p.planned) },
    { k: 'Duplicates skipped', v: formatCount(p.duplicates_skipped) },
    { k: 'Already organized', v: formatCount(p.already_organized) },
  ]
  if (p.undated > 0) rows.push({ k: 'Without capture date', v: formatCount(p.undated) })
  rows.push({ k: 'Est. space', v: formatBytes(p.est_bytes) })
  return rows
})

const applyDisabled = computed(
  () =>
    store.phase === 'running' ||
    store.previewLoading ||
    (store.preview?.planned ?? 0) === 0,
)
</script>

<template>
  <aside class="panel">
    <div class="top">
      <div class="label">PREVIEW</div>
      <div class="big">{{ formatCount(store.preview?.planned ?? 0) }}</div>
      <div class="big-sub">photos will be organized</div>

      <template v-if="examples.length">
        <div class="mini-label">Example destinations</div>
        <div class="examples">
          <div v-for="ex in examples" :key="ex.path" class="example" :title="ex.path">
            <span class="example-leaf">{{ ex.leaf }}</span>{{ ex.rest }}
          </div>
        </div>
      </template>
    </div>

    <div class="rule" />

    <div class="bottom">
      <div v-for="row in summary" :key="row.k" class="sum-row">
        <span class="sum-k">{{ row.k }}</span>
        <span class="sum-v">{{ row.v }}</span>
      </div>

      <div v-if="store.phase === 'running'" class="progress">
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${store.progressPct}%` }" />
        </div>
        <p class="progress-text">
          Moving {{ formatCount(store.activeRun?.moved ?? 0) }} /
          {{ formatCount(store.activeRun?.planned ?? 0) }}…
        </p>
      </div>
      <button v-else type="button" class="apply" :disabled="applyDisabled" @click="store.apply()">
        Organize {{ formatCount(store.preview?.planned ?? 0) }} photos →
      </button>
    </div>
  </aside>
</template>

<style scoped>
.panel {
  width: 340px;
  flex: none;
  display: flex;
  flex-direction: column;
  background: var(--sidebar);
  border-left: 1px solid var(--border);
  overflow: auto;
}

.top {
  padding: 20px 20px 0;
}

.label {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--muted);
  margin-bottom: 16px;
}

.big {
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.02em;
  font-family: var(--font-mono);
  line-height: 1;
}

.big-sub {
  font-size: 12.5px;
  color: var(--sub);
  margin-top: 4px;
  margin-bottom: 18px;
}

.mini-label {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 8px;
}

.examples {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 12px 13px;
  margin-bottom: 18px;
}

.example {
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.7;
  color: var(--sub);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.example-leaf {
  color: var(--fg);
}

.rule {
  margin: 0 20px;
  height: 1px;
  background: var(--divider);
}

.bottom {
  padding: 16px 20px 20px;
}

.sum-row {
  display: flex;
  justify-content: space-between;
  padding: 7px 0;
  font-size: 12.5px;
  border-bottom: 1px solid var(--divider);
}

.sum-k {
  color: var(--muted);
}

.sum-v {
  font-weight: 600;
  font-family: var(--font-mono);
}

.apply {
  margin-top: 16px;
  width: 100%;
  height: 44px;
  border: 0;
  border-radius: 11px;
  background: var(--accent);
  color: var(--on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

.apply:disabled {
  opacity: 0.45;
  cursor: default;
}

.progress {
  margin-top: 16px;
}

.progress-track {
  height: 6px;
  border-radius: 3px;
  background: var(--chip);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.12s linear;
}

.progress-text {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--sub);
  font-family: var(--font-mono);
}
</style>
