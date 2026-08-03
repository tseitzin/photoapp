import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { backfillGps } from '@/api/maintenance'
import { useLibraryStore } from '@/stores/library'

const CHUNK = 1000

/**
 * The GPS backfill: give coordinates to photos indexed before the scanner
 * extracted them.
 *
 * The server walks the library by id cursor and reads only EXIF headers, so
 * this store's job is to keep calling until the cursor runs out, report
 * progress, and let the user stop.
 */
export const useMaintenanceStore = defineStore('maintenance', () => {
  const library = useLibraryStore()

  const running = ref(false)
  const processed = ref(0)
  const updated = ref(0)
  const remaining = ref(0)
  const error = ref<string | null>(null)
  const finished = ref(false)
  let cancelled = false

  const summary = computed(() =>
    finished.value && !running.value
      ? `Checked ${processed.value.toLocaleString('en-US')} photos, ` +
        `found locations for ${updated.value.toLocaleString('en-US')}`
      : null,
  )

  async function run(): Promise<void> {
    if (running.value) return
    running.value = true
    finished.value = false
    cancelled = false
    processed.value = 0
    updated.value = 0
    remaining.value = 0
    error.value = null
    try {
      let cursor = 0
      for (;;) {
        const result = await backfillGps(cursor, CHUNK)
        processed.value += result.processed
        updated.value += result.updated
        remaining.value = result.remaining
        if (cancelled || result.next_after_id === null) break
        cursor = result.next_after_id
      }
      finished.value = true
      // Coordinates are part of every photo payload, so the open Library is
      // now showing stale rows.
      if (updated.value > 0 && library.hasLoaded) await library.reload().catch(() => {})
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      running.value = false
    }
  }

  /** Stop after the chunk in flight; work already done is kept. */
  function cancel(): void {
    cancelled = true
  }

  return { running, processed, updated, remaining, error, finished, summary, run, cancel }
})
