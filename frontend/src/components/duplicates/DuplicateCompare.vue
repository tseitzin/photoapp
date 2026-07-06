<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getPhoto, previewUrl, thumbnailUrl, type PhotoDetail } from '@/api/photos'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { useDuplicatesStore } from '@/stores/duplicates'
import { formatBytes, formatCount, formatDate } from '@/utils/format'

const store = useDuplicatesStore()

const details = ref<Record<number, PhotoDetail>>({})
const confirmingRemoveBoth = ref(false)

async function removeBoth(): Promise<void> {
  confirmingRemoveBoth.value = false
  await store.decide('remove_both')
}

// Fade the full preview in once it decodes; until then (or if it fails) the
// cached thumbnail behind it stays visible.
function markLoaded(event: Event): void {
  ;(event.target as HTMLImageElement).classList.add('loaded')
}

watch(
  () => store.currentPair,
  async (pair) => {
    if (!pair) return
    for (const member of [pair.a, pair.b]) {
      const id = member.photo.id
      if (!details.value[id]) {
        try {
          details.value[id] = await getPhoto(id)
        } catch {
          /* sha row shows an em dash */
        }
      }
    }
  },
  { immediate: true },
)

const similarity = computed(() =>
  store.currentPair?.group.kind === 'exact' ? 100 : (store.currentPair?.b.similarity_pct ?? 0),
)

const dialLabel = computed(() => {
  if (!store.currentPair) return ''
  if (store.currentPair.group.kind === 'exact') return 'Pixel-identical'
  return 'Visually similar'
})

function dirname(path: string): string {
  return path.slice(0, path.lastIndexOf('/'))
}

interface DiffRow {
  label: string
  a: string
  b: string
}

const rows = computed<DiffRow[]>(() => {
  const pair = store.currentPair
  if (!pair) return []
  const [a, b] = [pair.a.photo, pair.b.photo]
  const sha = (id: number) => details.value[id]?.sha256?.slice(0, 12) ?? '—'
  return [
    {
      label: 'Dimensions',
      a: a.width ? `${a.width} × ${a.height}` : '—',
      b: b.width ? `${b.width} × ${b.height}` : '—',
    },
    { label: 'File size', a: formatBytes(a.size_bytes), b: formatBytes(b.size_bytes) },
    { label: 'Format', a: a.ext.toUpperCase(), b: b.ext.toUpperCase() },
    { label: 'Captured', a: formatDate(a.captured_at), b: formatDate(b.captured_at) },
    { label: 'SHA-256', a: sha(a.id), b: sha(b.id) },
    { label: 'Folder', a: dirname(a.path), b: dirname(b.path) },
  ]
})
</script>

<template>
  <div v-if="store.currentPair" class="compare">
    <div class="progress-row">
      <div class="progress-track">
        <div
          class="progress-fill"
          :style="{ width: `${(store.resolvedPairs / Math.max(1, store.totalPairs)) * 100}%` }"
        />
      </div>
      <span class="progress-text">
        Pair {{ formatCount(store.resolvedPairs + 1) }} / {{ formatCount(store.totalPairs) }}
      </span>
      <span class="chip">
        {{ store.resolvedPairs }} resolved · {{ formatBytes(store.freedBytes) }} to free
      </span>
      <button type="button" class="btn btn--ghost" @click="store.stopReview()">
        Back to groups
      </button>
    </div>

    <div class="panes">
      <figure class="pane">
        <figcaption class="tag tag--keep">Suggested keeper</figcaption>
        <div
          class="pane-image"
          :style="{ backgroundImage: `url(${thumbnailUrl(store.currentPair.a.photo.id)})` }"
        >
          <img
            :key="store.currentPair.a.photo.id"
            class="pane-preview"
            :src="previewUrl(store.currentPair.a.photo.id)"
            :alt="store.currentPair.a.photo.filename"
            @load="markLoaded"
          />
        </div>
        <p class="pane-name">{{ store.currentPair.a.photo.filename }}</p>
      </figure>

      <div class="middle">
        <div
          class="dial"
          role="img"
          :aria-label="`${similarity}% match`"
          :style="{ '--pct': similarity }"
        >
          <div class="dial-inner">
            <span class="dial-value">{{ similarity }}%</span>
          </div>
        </div>
        <p class="dial-label">{{ dialLabel }}</p>

        <table class="diff">
          <tbody>
            <tr v-for="row in rows" :key="row.label" :class="{ differs: row.a !== row.b }">
              <th>{{ row.label }}</th>
              <td>{{ row.a }}</td>
              <td class="b-value">{{ row.b }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <figure class="pane">
        <figcaption
          class="tag"
          :class="store.currentPair.group.kind === 'exact' ? 'tag--dupe' : 'tag--similar'"
        >
          {{ store.currentPair.group.kind === 'exact' ? 'Exact duplicate' : 'Visually similar' }}
        </figcaption>
        <div
          class="pane-image"
          :style="{ backgroundImage: `url(${thumbnailUrl(store.currentPair.b.photo.id)})` }"
        >
          <img
            :key="store.currentPair.b.photo.id"
            class="pane-preview"
            :src="previewUrl(store.currentPair.b.photo.id)"
            :alt="store.currentPair.b.photo.filename"
            @load="markLoaded"
          />
        </div>
        <p class="pane-name">{{ store.currentPair.b.photo.filename }}</p>
      </figure>
    </div>

    <footer class="actions">
      <button type="button" class="btn btn--keep" @click="store.decide('keep_a')">Keep A</button>
      <button type="button" class="btn" @click="store.decide('keep_b')">Keep B</button>
      <button type="button" class="btn" @click="store.decide('keep_both')">Keep both</button>
      <button type="button" class="btn btn--danger" @click="confirmingRemoveBoth = true">
        Remove both
      </button>
      <span class="reclaim">
        Removing B marks {{ formatBytes(store.currentPair.b.photo.size_bytes) }} for quarantine
      </span>
      <button type="button" class="btn btn--ghost" @click="store.skip()">Skip →</button>
    </footer>

    <ConfirmDialog
      v-if="confirmingRemoveBoth"
      title="Remove both photos?"
      confirm-label="Remove both"
      danger
      @confirm="removeBoth"
      @cancel="confirmingRemoveBoth = false"
    >
      <p>
        Both <strong>{{ store.currentPair.a.photo.filename }}</strong> and
        <strong>{{ store.currentPair.b.photo.filename }}</strong> will be marked for removal —
        neither is kept. They go to the removal work-list, where you quarantine and then
        permanently delete them (reversible until you delete for good).
      </p>
    </ConfirmDialog>
  </div>
</template>

<style scoped>
.compare {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 14px 22px 18px;
  gap: 14px;
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-track {
  flex: 1;
  height: 5px;
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
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--sub);
  white-space: nowrap;
}

.chip {
  font-size: 11.5px;
  padding: 4px 10px;
  border-radius: 7px;
  background: var(--chip);
  color: var(--sub);
  white-space: nowrap;
}

.panes {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 300px 1fr;
  gap: 18px;
}

.pane {
  margin: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pane-image {
  flex: 1;
  min-height: 0;
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  /* Cached thumbnail shown instantly; the full preview fades in over it. */
  background-color: var(--grid-bg);
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
}

.pane-preview {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.pane-preview.loaded {
  opacity: 1;
}

.pane-name {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--sub);
  text-align: center;
  word-break: break-all;
}

.tag {
  align-self: center;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 6px;
  color: #fff;
}

.tag--keep {
  background: var(--success);
}

.tag--dupe {
  background: var(--danger);
}

.tag--similar {
  background: var(--accent);
  color: var(--on-accent);
}

.middle {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  overflow: auto;
}

.dial {
  width: 110px;
  height: 110px;
  border-radius: 50%;
  background: conic-gradient(
    var(--accent) calc(var(--pct) * 1%),
    var(--chip) 0
  );
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 8px;
}

.dial-inner {
  width: 86px;
  height: 86px;
  border-radius: 50%;
  background: var(--card);
  display: flex;
  align-items: center;
  justify-content: center;
}

.dial-value {
  font-family: var(--font-mono);
  font-size: 20px;
  font-weight: 700;
}

.dial-label {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--sub);
}

.diff {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.diff th {
  text-align: left;
  font-weight: 500;
  color: var(--sub);
  padding: 6px 8px;
  white-space: nowrap;
}

.diff td {
  padding: 6px 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  word-break: break-all;
}

.diff tr {
  border-top: 1px solid var(--divider);
}

.diff tr.differs {
  background: color-mix(in oklab, var(--danger) 8%, transparent);
}

.diff tr.differs .b-value {
  color: var(--danger);
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn {
  padding: 8px 18px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--chip);
  color: var(--fg);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.btn--keep {
  background: var(--success);
  border-color: var(--success);
  color: #fff;
  font-weight: 600;
}

.btn--danger {
  background: transparent;
  border-color: var(--danger);
  color: var(--danger);
  font-weight: 600;
}

.btn--ghost {
  background: transparent;
  border-color: transparent;
  color: var(--sub);
}

.reclaim {
  flex: 1;
  text-align: right;
  font-size: 12px;
  color: var(--muted);
}

@media (max-width: 900px) {
  .panes {
    grid-template-columns: 1fr;
    grid-auto-rows: minmax(200px, auto);
  }
}
</style>
