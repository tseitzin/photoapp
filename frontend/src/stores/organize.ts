import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  getLibraryLayout,
  getOrganizeRun,
  listOrganizeRuns,
  previewOrganize,
  startOrganize,
  TERMINAL_ORGANIZE_STATUSES,
  type LibraryLocation,
  type OrganizeMode,
  type OrganizePreview,
  type OrganizeRequest,
  type OrganizeRun,
} from '@/api/organize'
import { useLibraryStore } from '@/stores/library'

const POLL_MS = 1000
// The preview is a server round-trip; settle before recomputing it.
const PREVIEW_DEBOUNCE_MS = 300

// Where the last run sent photos, and how. Remembered across sessions because
// the choice is stable: recomputing a default on each visit once silently
// retargeted a run at a folder the user had just added.
export const ORGANIZE_PREFS_KEY = 'aperture-organize-prefs'

const MODES: OrganizeMode[] = ['keep', 'date', 'camera']

function storedPrefs(): {
  destination?: string
  mode?: OrganizeMode
  rename?: boolean
  skipDuplicates?: boolean
} {
  try {
    const raw = localStorage.getItem(ORGANIZE_PREFS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return {}
    const p = parsed as Record<string, unknown>
    return {
      destination: typeof p.destination === 'string' ? p.destination : undefined,
      mode: MODES.includes(p.mode as OrganizeMode) ? (p.mode as OrganizeMode) : undefined,
      rename: typeof p.rename === 'boolean' ? p.rename : undefined,
      skipDuplicates: typeof p.skipDuplicates === 'boolean' ? p.skipDuplicates : undefined,
    }
  } catch {
    return {} // unreadable or corrupt storage falls back to defaults
  }
}

export type OrganizePhase = 'setup' | 'running' | 'done'

export const useOrganizeStore = defineStore('organize', () => {
  const library = useLibraryStore()
  const saved = storedPrefs()

  const destination = ref(saved.destination ?? '')
  const mode = ref<OrganizeMode>(saved.mode ?? 'keep')
  const rename = ref(saved.rename ?? false)
  const skipDuplicates = ref(saved.skipDuplicates ?? true)
  const preview = ref<OrganizePreview | null>(null)
  const previewLoading = ref(false)
  const error = ref<string | null>(null)
  const activeRun = ref<OrganizeRun | null>(null)
  const phase = ref<OrganizePhase>('setup')
  const pickerOpen = ref(false)
  /** Where the library lives today, biggest location first. */
  const locations = ref<LibraryLocation[]>([])

  /** The place most of the library already sits, if there is one. */
  const dominantLocation = computed<LibraryLocation | null>(() => locations.value[0] ?? null)

  /**
   * True when organizing into the chosen destination would leave the library
   * in more than one place.
   *
   * Nothing compared these before, which is how a library ended up as the same
   * date structure in two locations — invisible until you went looking.
   */
  const wouldSplitLibrary = computed(() => {
    const dominant = dominantLocation.value
    if (!dominant || !destination.value) return false
    return destination.value.replace(/\/+$/, '') !== dominant.path.replace(/\/+$/, '')
  })

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

  /** First-run fallback only — once the user picks a destination it is
   * remembered. Prefer an existing "Organized"-style root over whichever
   * folder happens to sort first, which is an arbitrary choice. */
  function defaultDestination(): string {
    const roots = library.folders.filter((node) => node.depth === 0)
    const organized = roots.find((node) => node.path.endsWith('/Organized'))
    if (organized) return organized.path
    const first = roots[0]
    return first ? `${first.path}/Organized` : ''
  }

  async function load(): Promise<void> {
    error.value = null
    try {
      if (library.folders.length === 0) await library.loadFolders()
      await refreshLayout()
      // Prefer where the library already is over a guess — picking anywhere
      // else is what splits it in two.
      if (!destination.value) destination.value = dominantLocation.value?.path ?? defaultDestination()
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

  async function refreshLayout(): Promise<void> {
    try {
      locations.value = (await getLibraryLayout()).locations
    } catch {
      // Advisory only: a missing layout must not block organizing.
      locations.value = []
    }
  }

  /** Point the destination at where the library already lives. */
  function useDominantLocation(): void {
    if (dominantLocation.value) destination.value = dominantLocation.value.path
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
    persistPrefs()
  })

  function persistPrefs(): void {
    try {
      localStorage.setItem(
        ORGANIZE_PREFS_KEY,
        JSON.stringify({
          destination: destination.value,
          mode: mode.value,
          rename: rename.value,
          skipDuplicates: skipDuplicates.value,
        }),
      )
    } catch {
      /* storage full or blocked: preferences just won't persist */
    }
  }

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
          // Paths changed on disk: the folder tree, the grid and where the
          // library lives are all stale.
          await Promise.all([
            library.loadFolders().catch(() => {}),
            library.reload().catch(() => {}),
            refreshLayout(),
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
    locations,
    dominantLocation,
    wouldSplitLibrary,
    workingSet,
    workingTotals,
    progressPct,
    load,
    refreshLayout,
    useDominantLocation,
    apply,
    removeFolder,
    discard,
    reset,
    stopPolling,
  }
})
