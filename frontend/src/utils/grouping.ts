import type { PhotoRead } from '@/api/photos'

export type GroupBy = 'folder' | 'date' | 'camera'

export interface PhotoSection {
  key: string
  title: string
  photos: PhotoRead[]
}

function dirname(path: string): string {
  const index = path.lastIndexOf('/')
  return index > 0 ? path.slice(0, index) : path
}

function monthLabel(iso: string | null): string {
  if (!iso) return 'No capture date'
  const date = new Date(iso)
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' })
}

function groupKey(photo: PhotoRead, groupBy: GroupBy): [string, string] {
  switch (groupBy) {
    case 'date': {
      const label = monthLabel(photo.captured_at)
      return [label, label]
    }
    case 'camera': {
      const camera = photo.camera_model ?? 'Unknown camera'
      return [camera, camera]
    }
    case 'folder': {
      const dir = dirname(photo.path)
      return [dir, dir.split('/').pop() || dir]
    }
  }
}

/** Group already-sorted photos into contiguous display sections. */
export function groupPhotos(photos: PhotoRead[], groupBy: GroupBy): PhotoSection[] {
  const sections: PhotoSection[] = []
  const byKey = new Map<string, PhotoSection>()
  for (const photo of photos) {
    const [key, title] = groupKey(photo, groupBy)
    let section = byKey.get(key)
    if (!section) {
      section = { key, title, photos: [] }
      byKey.set(key, section)
      sections.push(section)
    }
    section.photos.push(photo)
  }
  return sections
}
