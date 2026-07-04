import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { THEME_STORAGE_KEY, useThemeStore } from '../theme'

describe('theme store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  it('restores the persisted theme on startup', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')

    const store = useThemeStore()

    expect(store.theme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('persists a toggle to localStorage and applies it to the document', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    const store = useThemeStore()

    store.toggle()

    expect(store.theme).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('ignores garbage in localStorage and still yields a valid theme', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'neon')

    const store = useThemeStore()

    expect(['light', 'dark']).toContain(store.theme)
  })
})
