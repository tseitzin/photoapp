<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { resetDeletionHistory } from '@/api/files'
import { listPhotos, thumbnailUrl, type PhotoRead } from '@/api/photos'
import { getStats, type Stats } from '@/api/stats'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { formatBytes, formatCount } from '@/utils/format'

const stats = ref<Stats | null>(null)
const recent = ref<PhotoRead[]>([])
const failed = ref(false)
const confirmingReset = ref(false)

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
})

async function refreshStats(): Promise<void> {
  try {
    stats.value = await getStats()
  } catch {
    failed.value = true
  }
}

async function confirmReset(): Promise<void> {
  confirmingReset.value = false
  try {
    await resetDeletionHistory()
    await refreshStats()
  } catch {
    failed.value = true
  }
}

onMounted(async () => {
  try {
    const [statsResult, recentPage] = await Promise.all([
      getStats(),
      listPhotos({ limit: 18, sort: 'added_desc', status: 'active' }),
    ])
    stats.value = statsResult
    recent.value = recentPage.items
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <div class="home">
    <p class="greeting">{{ greeting }}</p>
    <h1 class="title">Your photo library</h1>

    <p v-if="failed" class="muted">Can’t reach the library service — stats unavailable.</p>

    <div class="stats">
      <div class="stat-card">
        <p class="stat-label">PHOTOS</p>
        <p class="stat-value">{{ stats ? formatCount(stats.photos) : '—' }}</p>
        <p class="stat-sub">{{ stats ? `${formatCount(stats.folders)} folders` : '' }}</p>
      </div>
      <div class="stat-card">
        <p class="stat-label">STORAGE</p>
        <p class="stat-value">{{ stats ? formatBytes(stats.storage_bytes) : '—' }}</p>
        <p class="stat-sub">indexed in place</p>
      </div>
      <div class="stat-card">
        <p class="stat-label">DUPLICATES</p>
        <p class="stat-value">{{ stats ? formatCount(stats.duplicate_photos) : '—' }}</p>
        <p class="stat-sub">
          {{ stats && stats.reclaimable_bytes ? `${formatBytes(stats.reclaimable_bytes)} reclaimable` : 'exact copies' }}
        </p>
      </div>
      <div class="stat-card">
        <p class="stat-label">MISSING</p>
        <p class="stat-value">{{ stats ? formatCount(stats.missing) : '—' }}</p>
        <p class="stat-sub">files gone from disk</p>
      </div>
      <div class="stat-card">
        <p class="stat-label">DELETED</p>
        <p class="stat-value">{{ stats ? formatCount(stats.deleted_count) : '—' }}</p>
        <p class="stat-sub">removed all-time</p>
      </div>
      <div class="stat-card">
        <p class="stat-label">SPACE SAVED</p>
        <p class="stat-value">{{ stats ? formatBytes(stats.space_saved_bytes) : '—' }}</p>
        <p class="stat-sub">reclaimed by deletion</p>
      </div>
    </div>

    <div class="stats-actions">
      <button
        type="button"
        class="reset-btn"
        :disabled="!stats"
        @click="confirmingReset = true"
      >
        Reset deletion counter
      </button>
    </div>

    <div class="entries">
      <RouterLink to="/library" class="entry">
        <div class="mosaic" aria-hidden="true">
          <img
            v-for="photo in recent.slice(0, 6)"
            :key="photo.id"
            :src="thumbnailUrl(photo.id)"
            alt=""
            loading="lazy"
          />
          <div v-for="i in Math.max(0, 6 - recent.length)" :key="`ph-${i}`" class="mosaic-ph" />
        </div>
        <p class="entry-title">Browse library</p>
        <p class="entry-sub">
          {{ stats ? `${formatCount(stats.photos)} photos · ${formatCount(stats.folders)} folders` : '' }}
        </p>
      </RouterLink>

      <RouterLink to="/duplicates" class="entry entry--accent">
        <div class="entry-glyph" aria-hidden="true">⧉</div>
        <p class="entry-title">
          Review duplicates
          <span v-if="stats?.reclaimable_bytes" class="badge">
            {{ formatBytes(stats.reclaimable_bytes) }} free
          </span>
        </p>
        <p class="entry-sub">
          {{ stats ? `${formatCount(stats.duplicate_photos)} duplicate photos` : '' }}
        </p>
      </RouterLink>

      <RouterLink to="/scan" class="entry">
        <div class="entry-glyph" aria-hidden="true">⌕</div>
        <p class="entry-title">Scan folders</p>
        <p class="entry-sub">
          {{ stats?.last_scan_at ? `Last scan ${new Date(stats.last_scan_at).toLocaleString()}` : 'No scans yet' }}
        </p>
      </RouterLink>
    </div>

    <div v-if="recent.length" class="recent">
      <div class="recent-header">
        <h2 class="recent-title">Recently indexed</h2>
        <RouterLink to="/library" class="recent-link">View all →</RouterLink>
      </div>
      <div class="recent-grid">
        <RouterLink v-for="photo in recent" :key="photo.id" to="/library" class="recent-tile">
          <img :src="thumbnailUrl(photo.id)" :alt="photo.filename" loading="lazy" />
        </RouterLink>
      </div>
    </div>

    <ConfirmDialog
      v-if="confirmingReset"
      title="Reset the deletion counter?"
      confirm-label="Reset to zero"
      @confirm="confirmReset"
      @cancel="confirmingReset = false"
    >
      <p>
        This sets <strong>Deleted</strong> and <strong>Space saved</strong> back to zero and
        clears the deletion history for photos already removed. It does not touch your library
        or any photos currently in quarantine — only the running tally is reset, and counting
        starts fresh from now.
      </p>
    </ConfirmDialog>
  </div>
</template>

<style scoped>
.home {
  max-width: 1180px;
  width: 100%;
  margin: 0 auto;
  padding: 36px 40px;
}

.greeting {
  margin: 0 0 2px;
  font-size: 13px;
  color: var(--muted);
}

.title {
  margin: 0 0 24px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.muted {
  color: var(--muted);
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px;
  margin-bottom: 26px;
}

.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 18px;
  box-shadow: var(--shadow-card);
}

.stat-label {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.stat-value {
  margin: 0 0 3px;
  font-family: var(--font-mono);
  font-size: 26px;
  font-weight: 700;
}

.stat-sub {
  margin: 0;
  font-size: 11.5px;
  color: var(--sub);
}

.stats-actions {
  display: flex;
  justify-content: flex-end;
  margin: -14px 0 26px;
}

.reset-btn {
  border: 0;
  background: transparent;
  color: var(--sub);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
}

.reset-btn:hover:not(:disabled) {
  color: var(--fg);
  background: var(--hover);
}

.reset-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.entries {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 30px;
}

.entry {
  display: block;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px;
  text-decoration: none;
  color: var(--fg);
  box-shadow: var(--shadow-card);
}

.entry:hover {
  border-color: var(--accent);
}

.entry--accent {
  border: 1.5px solid var(--accent);
  box-shadow: 0 2px 10px color-mix(in oklab, var(--accent) 25%, transparent);
}

.mosaic {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  margin-bottom: 12px;
}

.mosaic img,
.mosaic-ph {
  aspect-ratio: 1;
  width: 100%;
  border-radius: 5px;
  object-fit: cover;
  background: var(--skeleton);
  display: block;
}

.entry-glyph {
  height: 72px;
  border-radius: 10px;
  background: color-mix(in oklab, var(--accent) 12%, var(--card));
  color: var(--accent);
  font-size: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.entry-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.badge {
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--success);
  color: #fff;
}

.entry-sub {
  margin: 0;
  font-size: 12px;
  color: var(--sub);
}

.recent-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}

.recent-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.recent-link {
  font-size: 12.5px;
  color: var(--accent);
  text-decoration: none;
}

.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
  gap: 9px;
}

.recent-tile {
  aspect-ratio: 1;
  border-radius: 4px;
  overflow: hidden;
  background: var(--skeleton);
}

.recent-tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* .stats uses auto-fit, so it reflows on its own; only .entries needs help. */
@media (max-width: 900px) {
  .entries {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 560px) {
  .entries {
    grid-template-columns: 1fr;
  }

  .home {
    padding: 24px 20px;
  }
}
</style>
