import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PhotoTile from '../PhotoTile.vue'
import type { PhotoRead } from '@/api/photos'

vi.mock('@/api/photos', () => ({
  thumbnailUrl: (id: number) => `/thumb/${id}`,
}))

function photo(id: number, marked = false): PhotoRead {
  return {
    id,
    root_id: 1,
    path: `/lib/p${id}.jpg`,
    filename: `p${id}.jpg`,
    ext: 'jpg',
    mime: 'image/jpeg',
    size_bytes: 1000,
    width: 100,
    height: 80,
    captured_at: null,
    camera_make: null,
    camera_model: null,
    status: 'active',
    marked_for_deletion: marked,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function mountTile(overrides: { marked?: boolean; selected?: boolean } = {}) {
  return mount(PhotoTile, {
    props: { photo: photo(7, overrides.marked ?? false), selected: overrides.selected ?? false },
  })
}

describe('PhotoTile', () => {
  it('shows the thumbnail and names the photo for screen readers', () => {
    const wrapper = mountTile()

    expect(wrapper.get('img').attributes('src')).toBe('/thumb/7')
    expect(wrapper.get('.tile-img').attributes('aria-label')).toBe('p7.jpg')
  })

  it('passes the click event up so the grid can read its modifier keys', async () => {
    const wrapper = mountTile()

    await wrapper.get('.tile-img').trigger('click', { shiftKey: true })

    const [event] = wrapper.emitted('select')![0] as [MouseEvent]
    expect(event.shiftKey).toBe(true)
  })

  it('double click asks to open rather than to select', async () => {
    const wrapper = mountTile()

    await wrapper.get('.tile-img').trigger('dblclick')

    expect(wrapper.emitted('open')).toHaveLength(1)
  })

  it('the mark badge does not also select the photo', async () => {
    const wrapper = mountTile()

    await wrapper.get('.mark-toggle').trigger('click')

    expect(wrapper.emitted('mark')).toHaveLength(1)
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('a selected tile shows the ring and the badge', () => {
    const wrapper = mountTile({ selected: true })

    expect(wrapper.get('.tile').classes()).toContain('tile--selected')
    expect(wrapper.find('.select-badge').exists()).toBe(true)
    expect(wrapper.get('.tile-img').attributes('aria-pressed')).toBe('true')
  })

  it('a marked tile stays visibly marked and offers to unmark', () => {
    const wrapper = mountTile({ marked: true })

    expect(wrapper.get('.tile').classes()).toContain('tile--marked')
    expect(wrapper.get('.mark-toggle').attributes('aria-label')).toBe('Unmark p7.jpg')
  })

  it('takes its selected state from a prop, never from the store', () => {
    // The whole point of the split: a tile that read the store directly would
    // re-render on every selection change anywhere in the library.
    const wrapper = mountTile({ selected: true })

    expect(wrapper.get('.tile').classes()).toContain('tile--selected')
    expect(PhotoTile.props).toBeDefined()
    expect(Object.keys(PhotoTile.props as object)).toEqual(['photo', 'selected'])
  })
})
