import { describe, expect, it } from 'vitest'
import { groupPhotos } from '../grouping'
import type { PhotoRead } from '@/api/photos'

function photo(overrides: Partial<PhotoRead>): PhotoRead {
  return {
    id: 1,
    root_id: 1,
    path: '/lib/a.jpg',
    filename: 'a.jpg',
    ext: 'jpg',
    mime: 'image/jpeg',
    size_bytes: 1000,
    width: 100,
    height: 100,
    captured_at: null,
    camera_make: null,
    camera_model: null,
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('groupPhotos', () => {
  it('groups by folder using the parent directory name', () => {
    const sections = groupPhotos(
      [
        photo({ id: 1, path: '/lib/2024/iceland/a.jpg' }),
        photo({ id: 2, path: '/lib/2024/iceland/b.jpg' }),
        photo({ id: 3, path: '/lib/2023/c.jpg' }),
      ],
      'folder',
    )

    expect(sections.map((s) => s.title)).toEqual(['iceland', '2023'])
    expect(sections[0]!.photos).toHaveLength(2)
  })

  it('groups by capture month with a bucket for missing dates', () => {
    const sections = groupPhotos(
      [
        photo({ id: 1, captured_at: '2024-05-01T10:00:00' }),
        photo({ id: 2, captured_at: '2024-05-20T10:00:00' }),
        photo({ id: 3, captured_at: null }),
      ],
      'date',
    )

    expect(sections.map((s) => s.title)).toEqual(['May 2024', 'No capture date'])
  })

  it('groups by camera with a bucket for unknown cameras', () => {
    const sections = groupPhotos(
      [
        photo({ id: 1, camera_model: 'A7 IV' }),
        photo({ id: 2, camera_model: null }),
        photo({ id: 3, camera_model: 'A7 IV' }),
      ],
      'camera',
    )

    expect(sections.map((s) => s.title)).toEqual(['A7 IV', 'Unknown camera'])
    expect(sections[0]!.photos.map((p) => p.id)).toEqual([1, 3])
  })
})
