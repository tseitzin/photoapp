import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  getFacets,
  listPhotos,
  markPhotos,
  unmarkPhotos,
  type Facets,
  type PhotoRead,
  type PhotoSort,
} from '@/api/photos'
import { listFolders, type FolderNode } from '@/api/folders'
import { groupPhotos, type GroupBy } from '@/utils/grouping'

export type PageSize = number | 'all'
export const PAGE_SIZE_OPTIONS: PageSize[] = [100, 250, 500, 1000, 'all']
// The backend caps a single response at 1000 rows; "all" pages through in
// chunks of this size.
const CHUNK_SIZE = 1000

export interface LibraryFilters {
  types: string[]
  cameras: string[]
  q: string
}

export const useLibraryStore = defineStore('library', () => {
  const photos = ref<PhotoRead[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const pageSize = ref<PageSize>(100)
  const page = ref(0) // 0-indexed

  const filters = reactive<LibraryFilters>({ types: [], cameras: [], q: '' })
  const sort = ref<PhotoSort>('captured_desc')
  const groupBy = ref<GroupBy>('folder')
  const tileSize = ref(112)

  const folders = ref<FolderNode[]>([])
  const facets = ref<Facets | null>(null)
  const expanded = ref(new Set<string>())
  const checkedFolders = ref(new Set<string>())
  // Clicking a folder name filters the grid to it (recursive); the checkbox
  // is the separate "selected for organizing" state.
  const activeFolder = ref<string | null>(null)
  const selectedPhotoId = ref<number | null>(null)
  const lightboxOpen = ref(false)
  const lightboxIndex = ref(0)

  const totalPages = computed(() =>
    pageSize.value === 'all' ? 1 : Math.max(1, Math.ceil(total.value / pageSize.value)),
  )
  // 1-indexed inclusive range for "showing X–Y of Z".
  const pageStart = computed(() =>
    total.value === 0 || pageSize.value === 'all' ? Math.min(1, total.value) : page.value * pageSize.value + 1,
  )
  const pageEnd = computed(() =>
    pageSize.value === 'all'
      ? total.value
      : Math.min(total.value, (page.value + 1) * pageSize.value),
  )
  const sections = computed(() => groupPhotos(photos.value, groupBy.value))
  const selectedPhoto = computed(
    () => photos.value.find((p) => p.id === selectedPhotoId.value) ?? null,
  )
  const hasActiveFilters = computed(
    () =>
      filters.types.length > 0 ||
      filters.cameras.length > 0 ||
      filters.q !== '' ||
      activeFolder.value !== null,
  )

  /** Checked folders excluding those covered by a checked ancestor (no double counting). */
  const checkedTopLevel = computed(() =>
    folders.value.filter((node) => {
      if (!checkedFolders.value.has(node.path)) return false
      let parent = node.parent_path
      while (parent) {
        if (checkedFolders.value.has(parent)) return false
        parent = folders.value.find((n) => n.path === parent)?.parent_path ?? null
      }
      return true
    }),
  )
  const checkedTotals = computed(() => ({
    folders: checkedFolders.value.size,
    photos: checkedTopLevel.value.reduce((sum, node) => sum + node.photo_count, 0),
  }))

  function fetchChunk(limit: number, offset: number) {
    return listPhotos({
      limit,
      offset,
      folder: activeFolder.value ?? undefined,
      types: filters.types,
      cameras: filters.cameras,
      q: filters.q || undefined,
      sort: sort.value,
      status: 'active',
    })
  }

  async function fetchCurrentPage(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      if (pageSize.value === 'all') {
        const accumulated: PhotoRead[] = []
        let offset = 0
        let count = 0
        do {
          const chunk = await fetchChunk(CHUNK_SIZE, offset)
          count = chunk.total
          accumulated.push(...chunk.items)
          offset += CHUNK_SIZE
        } while (offset < count)
        photos.value = accumulated
        total.value = count
      } else {
        const result = await fetchChunk(pageSize.value, page.value * pageSize.value)
        photos.value = result.items
        total.value = result.total
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      photos.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  /** Reset to the first page and refetch — used after any filter/sort change. */
  async function reload(): Promise<void> {
    page.value = 0
    await fetchCurrentPage()
  }

  async function goToPage(target: number): Promise<void> {
    const clamped = Math.max(0, Math.min(target, totalPages.value - 1))
    if (clamped === page.value) return
    page.value = clamped
    await fetchCurrentPage()
  }

  function nextPage(): Promise<void> {
    return goToPage(page.value + 1)
  }

  function prevPage(): Promise<void> {
    return goToPage(page.value - 1)
  }

  async function setPageSize(value: PageSize): Promise<void> {
    if (value === pageSize.value) return
    pageSize.value = value
    page.value = 0
    await fetchCurrentPage()
  }

  async function loadFolders(): Promise<void> {
    folders.value = await listFolders()
    // Roots start expanded so the tree is immediately useful.
    for (const node of folders.value) {
      if (node.depth === 0) expanded.value.add(node.path)
    }
  }

  async function loadFacets(): Promise<void> {
    facets.value = await getFacets()
  }

  async function init(): Promise<void> {
    await Promise.all([reload(), loadFolders().catch(() => {}), loadFacets().catch(() => {})])
  }

  function toggleExpanded(path: string): void {
    const next = new Set(expanded.value)
    if (!next.delete(path)) next.add(path)
    expanded.value = next
  }

  /** Filter the grid to a folder (recursive); clicking it again shows all photos. */
  function setFolder(path: string | null): Promise<void> {
    activeFolder.value = activeFolder.value === path ? null : path
    return reload()
  }

  function toggleChecked(path: string): void {
    const next = new Set(checkedFolders.value)
    if (!next.delete(path)) next.add(path)
    checkedFolders.value = next
  }

  /** Uncheck a folder and every checked folder nested inside it. */
  function uncheckSubtree(path: string): void {
    const next = new Set(
      [...checkedFolders.value].filter((p) => p !== path && !p.startsWith(`${path}/`)),
    )
    checkedFolders.value = next
  }

  function clearChecked(): void {
    checkedFolders.value = new Set()
  }

  function toggleType(value: string): Promise<void> {
    const index = filters.types.indexOf(value)
    if (index === -1) filters.types.push(value)
    else filters.types.splice(index, 1)
    return reload()
  }

  function toggleCamera(value: string): Promise<void> {
    const index = filters.cameras.indexOf(value)
    if (index === -1) filters.cameras.push(value)
    else filters.cameras.splice(index, 1)
    return reload()
  }

  function setSearch(q: string): Promise<void> {
    filters.q = q
    return reload()
  }

  function clearFilters(): Promise<void> {
    filters.types = []
    filters.cameras = []
    filters.q = ''
    activeFolder.value = null
    return reload()
  }

  function setSort(value: PhotoSort): Promise<void> {
    sort.value = value
    return reload()
  }

  function setGroupBy(value: GroupBy): void {
    groupBy.value = value
  }

  function selectPhoto(id: number | null): void {
    selectedPhotoId.value = id
  }

  const markedOnPage = computed(
    () => photos.value.filter((p) => p.marked_for_deletion).length,
  )

  /** Flag/unflag a photo for deletion; updates the tile badge optimistically. */
  async function toggleMark(photoId: number): Promise<void> {
    const photo = photos.value.find((p) => p.id === photoId)
    if (!photo) return
    const willMark = !photo.marked_for_deletion
    photo.marked_for_deletion = willMark // optimistic
    try {
      await (willMark ? markPhotos([photoId]) : unmarkPhotos([photoId]))
    } catch (e) {
      photo.marked_for_deletion = !willMark // revert on failure
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  const lightboxPhoto = computed(() => photos.value[lightboxIndex.value] ?? null)

  function openLightbox(photoId: number): void {
    const index = photos.value.findIndex((p) => p.id === photoId)
    if (index === -1) return
    lightboxIndex.value = index
    selectedPhotoId.value = photoId
    lightboxOpen.value = true
  }

  function closeLightbox(): void {
    lightboxOpen.value = false
  }

  function lightboxStep(delta: 1 | -1): void {
    // The lightbox navigates within the currently loaded page of photos.
    const next = lightboxIndex.value + delta
    if (next < 0 || next >= photos.value.length) return
    lightboxIndex.value = next
    selectedPhotoId.value = photos.value[next]!.id
  }

  return {
    photos,
    total,
    loading,
    error,
    pageSize,
    page,
    totalPages,
    pageStart,
    pageEnd,
    filters,
    sort,
    groupBy,
    tileSize,
    folders,
    facets,
    expanded,
    checkedFolders,
    checkedTopLevel,
    checkedTotals,
    activeFolder,
    selectedPhotoId,
    selectedPhoto,
    lightboxOpen,
    lightboxIndex,
    lightboxPhoto,
    openLightbox,
    closeLightbox,
    lightboxStep,
    sections,
    hasActiveFilters,
    init,
    reload,
    loadFolders,
    goToPage,
    nextPage,
    prevPage,
    setPageSize,
    toggleExpanded,
    toggleChecked,
    setFolder,
    uncheckSubtree,
    clearChecked,
    toggleType,
    toggleCamera,
    setSearch,
    clearFilters,
    setSort,
    setGroupBy,
    selectPhoto,
    toggleMark,
    markedOnPage,
  }
})
