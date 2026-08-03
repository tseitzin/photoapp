import { ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError } from '@/api/client'
import { listMarkedForRemoval } from '@/api/duplicates'
import {
  deletePhotosPermanently,
  listFileOperations,
  quarantinePhotos,
  restorePhotos,
  type BatchResult,
  type FileOperation,
} from '@/api/files'
import { listPhotos, type PhotoRead } from '@/api/photos'
import { useLibraryStore } from '@/stores/library'

export const useQuarantineStore = defineStore('quarantine', () => {
  const library = useLibraryStore()

  const marked = ref<PhotoRead[]>([])
  const quarantined = ref<PhotoRead[]>([])
  const quarantinedTotal = ref(0)
  const operations = ref<FileOperation[]>([])
  const operationsTotal = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastBatch = ref<BatchResult | null>(null)
  /** Backend 409 message when a batch would wipe whole duplicate groups. */
  const forceWarning = ref<string | null>(null)

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [markedResult, quarantinedPage, opsPage] = await Promise.all([
        listMarkedForRemoval(),
        // High limit so "select all" covers the whole quarantine in one view.
        listPhotos({ status: 'quarantined', limit: 1000 }),
        listFileOperations(50),
      ])
      marked.value = markedResult
      quarantined.value = quarantinedPage.items
      quarantinedTotal.value = quarantinedPage.total
      operations.value = opsPage.items
      operationsTotal.value = opsPage.total
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function applyRemovals(force = false): Promise<boolean> {
    if (!marked.value.length) return false
    error.value = null
    forceWarning.value = null
    try {
      lastBatch.value = await quarantinePhotos(
        marked.value.map((photo) => photo.id),
        force,
      )
      await load()
      await refreshLibrary()
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        forceWarning.value = e.message
      } else {
        error.value = e instanceof Error ? e.message : String(e)
      }
      return false
    }
  }

  function clearForceWarning(): void {
    forceWarning.value = null
  }

  /**
   * These actions move photos in and out of the active set, so the Library's
   * cached page, folder counts and facets are all stale afterwards. Without
   * this, deleted photos sat on the grid with broken thumbnails until a manual
   * reload. Only refresh what has already been loaded, and never let a refresh
   * failure mask the outcome of the operation itself.
   */
  async function refreshLibrary(): Promise<void> {
    if (!library.hasLoaded) return // never opened — nothing cached to go stale
    await Promise.all([
      library.reload().catch(() => {}),
      library.loadFolders().catch(() => {}),
      library.loadFacets().catch(() => {}),
    ])
  }

  async function restore(photoIds: number[]): Promise<void> {
    if (!photoIds.length) return
    error.value = null
    try {
      lastBatch.value = await restorePhotos(photoIds)
      await load()
      await refreshLibrary()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function deletePermanently(photoIds: number[]): Promise<void> {
    if (!photoIds.length) return
    error.value = null
    try {
      // confirm=true is only ever sent from here, after the UI's typed
      // confirmation dialog has been completed.
      lastBatch.value = await deletePhotosPermanently(photoIds, true)
      await load()
      await refreshLibrary()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  return {
    marked,
    quarantined,
    quarantinedTotal,
    operations,
    operationsTotal,
    loading,
    error,
    lastBatch,
    forceWarning,
    load,
    applyRemovals,
    clearForceWarning,
    restore,
    deletePermanently,
  }
})
