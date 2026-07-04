import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  cancelScan,
  getScan,
  listScans,
  startScan,
  TERMINAL_SCAN_STATUSES,
  type ScanRead,
} from '@/api/scans'
import {
  createScanRoot,
  deleteScanRoot,
  listScanRoots,
  type ScanRoot,
} from '@/api/scanRoots'

const POLL_MS = 1000

export type ScanPhase = 'setup' | 'scanning' | 'done'

export const useScanStore = defineStore('scan', () => {
  const phase = ref<ScanPhase>('setup')
  const roots = ref<ScanRoot[]>([])
  const selectedRootIds = ref(new Set<number>())
  const activeScan = ref<ScanRead | null>(null)
  const error = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | undefined

  const progressPct = computed(() => {
    const scan = activeScan.value
    if (!scan || scan.files_found === 0) return 0
    return Math.min(100, Math.round((scan.files_processed / scan.files_found) * 100))
  })

  async function load(): Promise<void> {
    error.value = null
    try {
      roots.value = await listScanRoots()
      if (selectedRootIds.value.size === 0) {
        selectedRootIds.value = new Set(roots.value.filter((r) => r.enabled).map((r) => r.id))
      }
      // Resume watching a scan that is already running (e.g. after navigation).
      const [latest] = await listScans(1)
      if (latest && !TERMINAL_SCAN_STATUSES.includes(latest.status)) {
        activeScan.value = latest
        phase.value = 'scanning'
        startPolling(latest.id)
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  function toggleRoot(id: number): void {
    const next = new Set(selectedRootIds.value)
    if (!next.delete(id)) next.add(id)
    selectedRootIds.value = next
  }

  async function addRoot(path: string): Promise<boolean> {
    error.value = null
    try {
      const root = await createScanRoot(path)
      roots.value = [...roots.value, root].sort((a, b) => a.path.localeCompare(b.path))
      selectedRootIds.value = new Set([...selectedRootIds.value, root.id])
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      return false
    }
  }

  async function removeRoot(id: number): Promise<void> {
    error.value = null
    try {
      await deleteScanRoot(id)
      roots.value = roots.value.filter((r) => r.id !== id)
      const next = new Set(selectedRootIds.value)
      next.delete(id)
      selectedRootIds.value = next
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function start(): Promise<void> {
    error.value = null
    try {
      const allSelected =
        selectedRootIds.value.size === roots.value.length ? null : [...selectedRootIds.value]
      const scan = await startScan(allSelected)
      activeScan.value = scan
      phase.value = 'scanning'
      startPolling(scan.id)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  function startPolling(scanId: number): void {
    stopPolling()
    pollTimer = setInterval(() => void poll(scanId), POLL_MS)
  }

  function stopPolling(): void {
    if (pollTimer !== undefined) clearInterval(pollTimer)
    pollTimer = undefined
  }

  async function poll(scanId: number): Promise<void> {
    try {
      const scan = await getScan(scanId)
      activeScan.value = scan
      if (TERMINAL_SCAN_STATUSES.includes(scan.status)) {
        stopPolling()
        if (scan.status === 'completed') {
          phase.value = 'done'
        } else {
          phase.value = 'setup'
          error.value =
            scan.status === 'failed' ? (scan.message ?? 'Scan failed') : 'Scan cancelled'
        }
      }
    } catch {
      /* transient poll failure: keep trying at the next tick */
    }
  }

  async function cancel(): Promise<void> {
    if (!activeScan.value) return
    try {
      await cancelScan(activeScan.value.id)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  function reset(): void {
    stopPolling()
    phase.value = 'setup'
    activeScan.value = null
    error.value = null
  }

  return {
    phase,
    roots,
    selectedRootIds,
    activeScan,
    error,
    progressPct,
    load,
    toggleRoot,
    addRoot,
    removeRoot,
    start,
    cancel,
    reset,
    stopPolling,
  }
})
