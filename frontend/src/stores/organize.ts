import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  getOrganizeRun,
  listOrganizeRuns,
  previewOrganize,
  startOrganize,
  TERMINAL_ORGANIZE_STATUSES,
  type OrganizeMode,
  type OrganizePreview,
  type OrganizeRequest,
  type OrganizeRun,
} from '@/api/organize'
import { useLibraryStore } from '@/stores/library'

const POLL_MS = 1000
// The preview is a server round-trip; settle before recomputing it.
const PREVIEW_DEBOUNCE_MS = 300

export type OrganizePhase = 'setup' | 'running' | 'done'

export const useOrganizeStore = defineStore('organize', () => {
  const library = useLibraryStore()

  const destination = ref('')
  const mode = ref<OrganizeMode>('keep')
  const rename = ref(false)
  const skipDuplicates = ref(true)
  const preview = ref<OrganizePreview | null>(null)
  const previewLoading = ref(false)
  const error = ref<string | null>(null)
  const activeRun = ref<OrganizeRun | null>(null)
  const phase = ref<OrganizePhase>('setup')
  const pickerOpen = ref(false)

  let pollTimer: ReturnType<typeof setInterval> | undefined
  let previewTimer: ReturnType<typeof setTimeout> | undefined
  let previewSeq = 0

  // The working set stays owned by the library store — the Library's folder
  // checkboxes are its single source of truth.
  const workingSet = computed(() => library.checkedTopLevel)
  const workingTotals = computed(() => library.checkedTotals)

  const requestBody = computed<OrganizeRequest>(() => ({
    folders: workingSet.value.map((node) => node.path),
    destination: destination.value,
    mode: mode.value,
    rename: rename.value,
    skip_duplicates: skipDuplicates.value,
  }))

  const progressPct = computed(() => {
    const run = activeRun.value
    if (!run || run.planned === 0) return 0
    return Math.min(100, Math.round((run.moved / run.planned) * 100))
  })

  function defaultDestination(): string {
    const root = library.folders.find((node) => node.depth === 0)
    return root ? `${root.path}/Organized` : ''
  }

  async function load(): Promise<void> {
    error.value = null
    try {
      if (library.folders.length === 0) await library.loadFolders()
      if (!destination.value) destination.value = defaultDestination()
      // Resume watching a run that is already going (e.g. after navigation).
      const [latest] = await listOrganizeRuns(1)
      if (latest && !TERMINAL_ORGANIZE_STATUSES.includes(latest.status)) {
        activeRun.value = latest
        phase.value = 'running'
        startPolling(latest.id)
      }
      schedulePreview()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  function schedulePreview(): void {
    clearTimeout(previewTimer)
    if (workingSet.value.length === 0 || !destination.value) {
      preview.value = null
      return
    }
    previewTimer = setTimeout(() => void refreshPreview(), PREVIEW_DEBOUNCE_MS)
  }

  async function refreshPreview(): Promise<void> {
    const seq = ++previewSeq
    previewLoading.value = true
    error.value = null
    try {
      const result = await previewOrganize(requestBody.value)
      if (seq === previewSeq) preview.value = result
    } catch (e) {
      if (seq === previewSeq) {
        preview.value = null
        error.value = e instanceof Error ? e.message : String(e)
      }
    } finally {
      if (seq === previewSeq) previewLoading.value = false
    }
  }

  // Any input change (working set, destination, mode, toggles) refreshes the
  // preview after the debounce; requestBody covers them all.
  watch(requestBody, () => {
    if (phase.value === 'setup') schedulePreview()
  })

  async function apply(): Promise<void> {
    error.value = null
    try {
      const run = await startOrganize(requestBody.value)
      activeRun.value = run
      phase.value = 'running'
      startPolling(run.id)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  function startPolling(runId: number): void {
    stopPolling()
    pollTimer = setInterval(() => void poll(runId), POLL_MS)
  }

  function stopPolling(): void {
    if (pollTimer !== undefined) clearInterval(pollTimer)
    pollTimer = undefined
  }

  async function poll(runId: number): Promise<void> {
    try {
      const run = await getOrganizeRun(runId)
      activeRun.value = run
      if (TERMINAL_ORGANIZE_STATUSES.includes(run.status)) {
        stopPolling()
        if (run.status === 'completed') {
          phase.value = 'done'
          preview.value = null
          // Paths changed on disk: the folder tree and the grid are both stale.
          await Promise.all([
            library.loadFolders().catch(() => {}),
            library.reload().catch(() => {}),
          ])
        } else {
          phase.value = 'setup'
          error.value = run.message ?? 'Organize failed'
        }
      }
    } catch {
      /* transient poll failure: keep trying at the next tick */
    }
  }

  function removeFolder(path: string): void {
    library.uncheckSubtree(path)
  }

  function discard(): void {
    stopPolling()
    clearTimeout(previewTimer)
    library.clearChecked()
    preview.value = null
    phase.value = 'setup'
    activeRun.value = null
    error.value = null
  }

  function reset(): void {
    stopPolling()
    phase.value = 'setup'
    activeRun.value = null
    error.value = null
    schedulePreview()
  }

  return {
    destination,
    mode,
    rename,
    skipDuplicates,
    preview,
    previewLoading,
    error,
    activeRun,
    phase,
    pickerOpen,
    workingSet,
    workingTotals,
    progressPct,
    load,
    apply,
    removeFolder,
    discard,
    reset,
    stopPolling,
  }
})
