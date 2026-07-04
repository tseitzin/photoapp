import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  getFacets,
  listPhotos,
  type Facets,
  type PhotoRead,
  type PhotoSort,
} from '@/api/photos'
import { listFolders, type FolderNode } from '@/api/folders'
import { groupPhotos, type GroupBy } from '@/utils/grouping'

const PAGE_SIZE = 100

export interface LibraryFilters {
  types: string[]
  cameras: string[]
  q: string
}

export const useLibraryStore = defineStore('library', () => {
  const photos = ref<PhotoRead[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref<string | null>(null)

  const filters = reactive<LibraryFilters>({ types: [], cameras: [], q: '' })
  const sort = ref<PhotoSort>('captured_desc')
  const groupBy = ref<GroupBy>('folder')
  const tileSize = ref(112)

  const folders = ref<FolderNode[]>([])
  const facets = ref<Facets | null>(null)
  const expanded = ref(new Set<string>())
  const checkedFolders = ref(new Set<string>())
  const selectedPhotoId = ref<number | null>(null)
  const lightboxOpen = ref(false)
  const lightboxIndex = ref(0)

  const hasMore = computed(() => photos.value.length < total.value)
  const sections = computed(() => groupPhotos(photos.value, groupBy.value))
  const selectedPhoto = computed(
    () => photos.value.find((p) => p.id === selectedPhotoId.value) ?? null,
  )
  const hasActiveFilters = computed(
    () => filters.types.length > 0 || filters.cameras.length > 0 || filters.q !== '',
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

  async function fetchPage(offset: number): Promise<void> {
    const page = await listPhotos({
      limit: PAGE_SIZE,
      offset,
      types: filters.types,
      cameras: filters.cameras,
      q: filters.q || undefined,
      sort: sort.value,
      status: 'active',
    })
    total.value = page.total
    photos.value = offset === 0 ? page.items : [...photos.value, ...page.items]
  }

  async function reload(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await fetchPage(0)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      photos.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  async function loadMore(): Promise<void> {
    if (loading.value || loadingMore.value || !hasMore.value) return
    loadingMore.value = true
    try {
      await fetchPage(photos.value.length)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loadingMore.value = false
    }
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

  function toggleChecked(path: string): void {
    const next = new Set(checkedFolders.value)
    if (!next.delete(path)) next.add(path)
    checkedFolders.value = next
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
    const next = lightboxIndex.value + delta
    if (next < 0 || next >= photos.value.length) return
    lightboxIndex.value = next
    selectedPhotoId.value = photos.value[next]!.id
    // Keep the runway ahead of the user when paging forward.
    if (delta === 1 && photos.value.length - next < 20) void loadMore()
  }

  return {
    photos,
    total,
    loading,
    loadingMore,
    error,
    filters,
    sort,
    groupBy,
    tileSize,
    folders,
    facets,
    expanded,
    checkedFolders,
    checkedTotals,
    selectedPhotoId,
    selectedPhoto,
    lightboxOpen,
    lightboxIndex,
    lightboxPhoto,
    openLightbox,
    closeLightbox,
    lightboxStep,
    hasMore,
    sections,
    hasActiveFilters,
    init,
    reload,
    loadMore,
    toggleExpanded,
    toggleChecked,
    toggleType,
    toggleCamera,
    setSearch,
    clearFilters,
    setSort,
    setGroupBy,
    selectPhoto,
  }
})
